"""The MCP layer: 8 servers, 11 tools, exactly the three writes marked destructiveHint, every tool reaching its
stand-in with the right method and path, and a failing stand-in turned into a tool error (never a crash) that keeps
the stand-in's Retry-After.

Tests use the servers' own objects (their tool listing and call_tool). They define no servers or clients of their own,
so a NaviStorm scan of this repo is the same with or without tests/."""
import importlib
import json

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

from stubs import stub_responses as R

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
    ("sap", "production_plan", {}, "GET", "http://stub-sap:8000/production_plan", R.PRODUCTION_PLAN),
    ("sap", "shift_confirm", {"shifts": []}, "POST", "http://stub-sap:8000/shift_confirm", R.SHIFT_CONFIRM_OK),
    ("workday", "absences", {}, "GET", "http://stub-workday:8000/absences", R.ABSENCES),
    ("workday", "workers", {}, "GET", "http://stub-workday:8000/workers", R.WORKERS),
    ("workday", "schedules", {"roster": {"sites": []}}, "POST", "http://stub-workday:8000/schedules", R.SCHEDULES_OK),
    ("mes", "line_availability", {}, "GET", "http://stub-mes:8000/line_availability", R.LINE_AVAILABILITY),
    ("lms", "training_currency", {}, "GET", "http://stub-lms:8000/training_currency", R.TRAINING_CURRENCY),
    ("cuopt", "solve", {"payload": {"workers": []}}, "POST", "http://stub-cuopt:8000/solve", R.SOLVE_OK),
    ("teams", "notify", {"payload": {"text": "hi"}}, "POST", "http://stub-teams:8000/notify", R.NOTIFY_ACCEPTED),
    ("policy", "rules", {}, "GET", "http://stub-policy:8000/rules", R.POLICY_RULES),
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
        route = mock.request(method, url).respond(202 if tool == "notify" else 200, json=canned)
        out = await server(name).call_tool(tool, args)
        assert route.called and _result(out) == canned
        if tool == "shift_confirm":
            assert route.calls[0].request.read() == b'{"shifts":[]}'


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


async def test_a_throttled_stand_in_passes_retry_after_on():
    """W1's demo: the error the agent sees says how long Workday asked it to wait (and the agent ignores it)."""
    with respx.mock() as mock:
        mock.get("http://stub-workday:8000/absences").respond(429, json=R.THROTTLED, headers={"Retry-After": "120"})
        with pytest.raises(ToolError, match=r"Workday answered HTTP 429 \(Retry-After: 120 s\)$"):
            await server("workday").call_tool("absences", {})


async def test_the_roster_store_answers_for_one_site():
    with respx.mock(assert_all_called=True) as mock:
        mock.get("http://stub-roster-store:8000/roster").respond(200, json=R.ROSTER_STORE_GET)
        one = _result(await server("roster").call_tool("store", {"site": "S03"}))
        assert one["site_id"] == "S03" and one["generated_at"] == "2026-11-20T03:58:00Z"
        assert [s["site_id"] for s in one["shifts"]] == ["S03"] and one["shifts"][0]["assigned"][0] == "W01"
        assert _result(await server("roster").call_tool("store", {"site": "S99"})) == {}


async def test_the_policy_server_reports_an_empty_answer_as_it_is():
    with respx.mock() as mock:
        mock.get("http://stub-policy:8000/rules").respond(200, json=R.POLICY_RULES_EMPTY)
        assert _result(await server("policy").call_tool("rules", {})) == R.POLICY_RULES_EMPTY
