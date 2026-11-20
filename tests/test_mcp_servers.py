"""The MCP layer: 8 servers, 11 tools, exactly the three writes marked destructiveHint, every tool reaching its
stand-in with the right method and path, and a failing stand-in turned into a tool error (never a crash).

Tests use the servers' own objects (their tool listing and call_tool). They define no servers or clients of their own,
so a NaviStorm scan of this repo is the same with or without tests/."""
import importlib
import json

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

SERVERS = ["sap", "workday", "mes", "lms", "cuopt", "teams", "policy", "roster"]
EXPECTED = {
    "sap": {"production_plan": "read", "shift_confirm": "write"},
    "workday": {"absences": "read", "workers": "read", "schedules": "write"},
    "mes": {"line_availability": "read"},
    "lms": {"training_currency": "read"},
    "cuopt": {"solve": "read"},
    "teams": {"notify": "write"},
    "policy": {"rules": "read"},
    "roster": {"store": "read"},
}


def server(name: str):
    return importlib.import_module(f"mcp_servers.{name}_server").mcp


async def tools_of(name: str) -> dict:
    return {t.name: t for t in await server(name).list_tools()}


async def test_eleven_tools_on_eight_servers_with_the_right_annotations():
    total = 0
    for name in SERVERS:
        tools = await tools_of(name)
        assert set(tools) == set(EXPECTED[name]), name
        for tname, kind in EXPECTED[name].items():
            a = tools[tname].annotations
            if kind == "write":
                assert a.destructiveHint is True and not a.readOnlyHint, f"{name}.{tname}"
            else:
                assert a.readOnlyHint is True and not a.destructiveHint, f"{name}.{tname}"
            assert tools[tname].description, f"{name}.{tname} says what it supplies"
        total += len(tools)
    assert total == 11


def test_servers_listen_where_compose_expects():
    for name in SERVERS:
        s = server(name).settings
        assert (s.host, s.port, s.streamable_http_path) == ("0.0.0.0", 9000, "/mcp"), name
        assert s.stateless_http and s.json_response


CALLS = [  # server, tool, arguments, method, stand-in URL, canned answer
    ("sap", "production_plan", {}, "GET", "http://stub-sap:8000/production_plan", ["site-01"]),
    ("sap", "shift_confirm", {"site": "site-01", "shifts": []}, "POST", "http://stub-sap:8000/shift_confirm", {"status": "ok"}),
    ("workday", "absences", {}, "GET", "http://stub-workday:8000/absences", [{"worker_id": "w001"}]),
    ("workday", "workers", {}, "GET", "http://stub-workday:8000/workers", [{"id": "w001"}]),
    ("workday", "schedules", {"roster": {"site-01": []}}, "POST", "http://stub-workday:8000/schedules", {"status": "ok"}),
    ("mes", "line_availability", {}, "GET", "http://stub-mes:8000/line_availability", [{"site": "site-01"}]),
    ("lms", "training_currency", {}, "GET", "http://stub-lms:8000/training_currency", [{"worker_id": "w001"}]),
    ("cuopt", "solve", {"payload": {"workers": []}}, "POST", "http://stub-cuopt:8000/solve", {"status": "OK", "roster": {}}),
    ("teams", "notify", {"payload": {"text": "hi"}}, "POST", "http://stub-teams:8000/notify", {"status": "ok"}),
]


def _result(out):
    """call_tool answers either (content blocks, structured result), or content blocks alone (a dict return value):
    the tool's return value, either way."""
    if isinstance(out, tuple):
        structured = out[1]
        return structured.get("result", structured) if isinstance(structured, dict) else structured
    texts = [getattr(b, "text", "") for b in out]
    return json.loads(texts[0]) if len(texts) == 1 else [json.loads(t) for t in texts]


@pytest.mark.parametrize("name,tool,args,method,url,canned", CALLS, ids=[f"{c[0]}.{c[1]}" for c in CALLS])
async def test_each_tool_reaches_its_stand_in(name, tool, args, method, url, canned):
    with respx.mock(assert_all_called=True) as mock:
        route = mock.request(method, url).respond(200, json=canned)
        out = await server(name).call_tool(tool, args)
        assert route.called and _result(out) == canned
        if method == "POST" and tool == "shift_confirm":
            assert route.calls[0].request.read() == b'{"site":"site-01","shifts":[]}'


@pytest.mark.parametrize("failure,expect", [
    (httpx.ConnectTimeout("slow"), "did not answer"),
    (httpx.ConnectError("refused"), "could not be reached"),
    ("503", "answered HTTP 503"),
])
async def test_a_failing_stand_in_becomes_a_tool_error(failure, expect):
    with respx.mock() as mock:
        r = mock.get("http://stub-workday:8000/absences")
        if failure == "503":
            r.respond(503)
        else:
            r.mock(side_effect=failure)
        with pytest.raises(ToolError, match=expect):
            await server("workday").call_tool("absences", {})


async def test_internal_servers_serve_their_own_data():
    rules = _result(await server("policy").call_tool("rules", {}))
    assert [r["id"] for r in rules][0] == "max_weekly_hours"
    roster = _result(await server("roster").call_tool("store", {"site": "site-03"}))
    assert roster["site"] == "site-03" and roster["published_at"].startswith("2026-11-19")
    assert _result(await server("roster").call_tool("store", {"site": "site-99"})) == {}
