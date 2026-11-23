"""The agents: which tools each node uses, the retry behaviour the brief asks for (exactly), the compliance loop, what
each stand-in failure mode does to a run, the copilot, business hours, the model, and that agents reach systems only
through MCP."""
import pathlib
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
from langchain_core.tools import ToolException
from openai import RateLimitError

from agents import compliance, forecast_demand, hours, llm, optimize_roster, writeback
from agents.manager_copilot import copilot, describe, site_in
from agents.supervisor import supervisor
from stubs import stub_responses as R

from .fakes import FakeTool, canned, patch_tools

ALL_SITES = [f"S{i:02d}" for i in range(1, 15)]


@pytest.fixture
def sleeps(monkeypatch):
    waited: list[float] = []

    async def fake_sleep(s):
        waited.append(s)
    monkeypatch.setattr("agents.forecast_demand.asyncio.sleep", fake_sleep)
    return waited


def rate_limited(retry_after: str = "30") -> RateLimitError:
    req = httpx.Request("POST", "https://example.invalid/openai")
    return RateLimitError("429", response=httpx.Response(429, headers={"retry-after": retry_after}, request=req), body=None)


# ---------------------------------------------------------------------------------------------- tools per node

async def test_each_node_asks_for_exactly_its_tools(monkeypatch):
    asked = patch_tools(monkeypatch, canned())
    out = await supervisor.ainvoke({})
    await copilot.ainvoke({"question": "Who works at S02?"})
    assert asked == [
        ("sap.production_plan", "mes.line_availability", "workday.absences"),
        ("workday.workers", "lms.training_currency", "cuopt.solve"),
        ("policy.rules", "lms.training_currency"),
        ("workday.schedules", "sap.shift_confirm", "teams.notify"),
        ("roster.store",),
    ]
    assert out["published"] and out["compliant"] and out["sites"] == ALL_SITES and out["rounds"] == 1


async def test_every_one_of_the_11_tools_is_called_and_each_write_once(monkeypatch):
    tools = canned()
    patch_tools(monkeypatch, tools)
    await supervisor.ainvoke({})
    await copilot.ainvoke({"question": "S05"})
    assert all(t.calls for t in tools.values()), [n for n, t in tools.items() if not t.calls]
    for write in ("schedules", "shift_confirm", "notify"):
        assert len(tools[write].calls) == 1, write
    (confirm,) = tools["shift_confirm"].calls
    assert [s["site_id"] for s in confirm["shifts"]] == ALL_SITES  # one confirmation for every site ("confirmed": 14)


# --------------------------------------------------------------------------------- W1: the deliberate defect

async def test_forecast_retries_forever_with_a_fixed_delay(monkeypatch, sleeps):
    tools = canned()
    tools["absences"] = FakeTool("absences", R.ABSENCES, fail=[ToolException("Workday answered HTTP 429")] * 50)
    patch_tools(monkeypatch, tools)
    out = await forecast_demand.forecast_demand({})
    assert len(sleeps) == 50 and set(sleeps) == {1.0}  # no cap, no back-off
    assert out["sites"] == ALL_SITES


async def test_forecast_ignores_the_retry_after_workday_sends(monkeypatch, sleeps):
    """The throttled stand-in's Retry-After reaches the agent in the tool error; the agent still waits 1 s."""
    tools = canned()
    throttled = ToolException("Workday answered HTTP 429 (Retry-After: 120 s)")
    tools["absences"] = FakeTool("absences", R.ABSENCES, fail=[throttled] * 5)
    patch_tools(monkeypatch, tools)
    await forecast_demand.forecast_demand({})
    assert sleeps == [1.0] * 5 and len(tools["absences"].calls) == 6  # asked for 120 s, waited 1 s, called again
    assert len(tools["production_plan"].calls) == 6  # and every retry asks SAP and MES again too


async def test_forecast_ignores_retry_after_from_the_model(monkeypatch, sleeps):
    patch_tools(monkeypatch, canned())
    calls = {"n": 0}

    class Throttled:
        async def ainvoke(self, prompt):
            calls["n"] += 1
            if calls["n"] <= 3:
                raise rate_limited("30")
            return type("R", (), {"content": '{"ok": true}'})()
    monkeypatch.setattr("agents.forecast_demand.llm", Throttled())
    await forecast_demand.forecast_demand({})
    assert sleeps == [1.0, 1.0, 1.0]  # Retry-After said 30 s; it waited 1 s each time


def test_the_defect_is_marked_and_still_unbounded():
    src = pathlib.Path("agents/forecast_demand.py").read_text()
    assert "DELIBERATE DEFECT W1" in src and "DO NOT FIX" in src
    assert "while True:" in src and "retry_after" not in src.lower().replace("retry-after", "")


async def test_forecast_also_retries_model_timeouts_and_server_errors(monkeypatch, sleeps):
    from openai import APITimeoutError
    patch_tools(monkeypatch, canned())
    calls = {"n": 0}

    class Flaky:
        async def ainvoke(self, prompt):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise APITimeoutError(request=httpx.Request("POST", "https://example.invalid"))
            return type("R", (), {"content": '{"ok": true}'})()
    monkeypatch.setattr("agents.forecast_demand.llm", Flaky())
    await forecast_demand.forecast_demand({})
    assert sleeps == [1, 1]


# ------------------------------------------------------------------------------------------------- the forecast

async def test_forecast_for_all_sites_and_for_one(monkeypatch):
    patch_tools(monkeypatch, canned())
    out = await forecast_demand.forecast_demand({})
    assert out["demand"]["S01"] == {"line": "S01-L1", "shift": "EARLY", "running": True, "headcount": 5, "absent": 1}
    assert out["demand"]["S04"]["absent"] == 1 and out["demand"]["S02"]["absent"] == 0
    assert out["forecast_note"].startswith("Demand S01: 5 people on S01-L1, early shift, 1 absent; S02: 5 people")
    assert out["forecast_ok"] is True  # the model's check ({"ok": true})
    one = await forecast_demand.forecast_demand({"only_site": "S07"})
    assert one["sites"] == ["S07"] and list(one["demand"]) == ["S07"]
    assert one["forecast_note"] == "Demand S07: 5 people on S07-L1, early shift."


async def test_a_line_that_is_not_running_needs_no_one(monkeypatch):
    tools = canned()
    lines = [dict(x, status="DOWN") if x["line_id"] == "S03-L1" else x for x in R.LINE_AVAILABILITY["lines"]]
    tools["line_availability"] = FakeTool("line_availability", {"as_of": "x", "lines": lines})
    patch_tools(monkeypatch, tools)
    out = await forecast_demand.forecast_demand({"only_site": "S03"})
    assert out["demand"]["S03"]["headcount"] == 0 and "S03-L1 not running, no one needed" in out["forecast_note"]


# ------------------------------------------------------------------------------------------- the optimizer

async def test_optimizer_gives_up_after_three_attempts(monkeypatch):
    tools = canned()
    tools["solve"] = FakeTool("solve", {}, fail=[ToolException("NVIDIA cuOpt answered HTTP 500")] * 10)
    patch_tools(monkeypatch, tools)
    with pytest.raises(ToolException):
        await optimize_roster.optimize_roster({"sites": ALL_SITES})
    assert len(tools["solve"].calls) == 3  # MAX_RETRIES = 2


async def test_optimizer_stops_after_max_iter_when_the_solver_refuses(monkeypatch):
    tools = canned()
    tools["solve"] = FakeTool("solve", R.SOLVE_INFEASIBLE)
    patch_tools(monkeypatch, tools)
    out = await optimize_roster.optimize_roster({"sites": ALL_SITES})
    assert len(tools["solve"].calls) == 4  # MAX_ITER = 4
    assert out == {"roster": [], "solver_status": "no answer after max_iter (INFEASIBLE)"}


async def test_optimizer_solves_all_sites_at_once(monkeypatch):
    tools = canned()
    patch_tools(monkeypatch, tools)
    await optimize_roster.optimize_roster({"sites": ["S01", "S02"], "demand": {"S01": {}, "S02": {}}})
    (payload,) = [c["payload"] for c in tools["solve"].calls]
    assert set(payload["demand"]) == {"S01", "S02"}  # W2: one solve for every site
    assert len(payload["workers"]) == 10 and all(q["status"] == "CURRENT" for q in payload["training"])


async def test_optimizer_keeps_only_the_sites_of_the_run(monkeypatch):
    patch_tools(monkeypatch, canned())
    out = await optimize_roster.optimize_roster({"sites": ["S07"]})
    assert [r["site_id"] for r in out["roster"]] == ["S07"]  # the solver answered for 14
    assert out["hours"] == {f"W{i:02d}": 37.5 for i in range(1, 11)}


# ------------------------------------------------------------------------------------------- compliance loop

async def test_compliance_fail_loops_back_and_stops_after_three_rounds(monkeypatch):
    tools = canned()
    patch_tools(monkeypatch, tools)
    monkeypatch.setenv("WPO_FORCE_COMPLIANCE_FAIL", "1")
    out = await supervisor.ainvoke({})
    assert out["rounds"] == 3 and not out["compliant"] and not out.get("published")
    assert len(tools["solve"].calls) == 3  # the optimizer ran once per round
    assert not tools["schedules"].calls  # nothing written


def test_breaches():
    rules = R.POLICY_RULES["rules"]
    roster = [{"site_id": "S01", "line_id": "S01-L1", "assigned": ["W01", "W11"]}]
    found = compliance.breaches(roster, rules, {"W01"}, {"W01": 37.5, "W11": 50})
    assert found == ["S01: W11 has no current qualification",
                     "S01: W11 is over the weekly hours limit (50 h, limit 48 h)"]
    assert compliance.breaches(R.SOLVE_OK["roster"], rules, {f"W{i:02d}" for i in range(1, 11)}, {}) == []
    assert compliance.breaches([], rules, set(), {}) == ["the solver returned no roster"]
    assert compliance.breaches(roster, [], {"W01"}, {}) == [
        "the policy service returned no rules, so the roster cannot be checked"]
    assert compliance.route_compliance({"compliant": True}) == "pass"
    assert compliance.route_compliance({"compliant": False, "rounds": 1}) == "fail"
    assert compliance.route_compliance({"compliant": False, "rounds": 3}) == "stop"


async def test_weekly_hours_reach_compliance(monkeypatch):
    patch_tools(monkeypatch, canned())
    out = await optimize_roster.optimize_roster({"sites": ["S01"]})
    assert out["hours"]["W01"] == 37.5
    found = (await compliance.compliance({"sites": ["S01"], "roster": out["roster"], "hours": {"W01": 50}}))["breaches"]
    assert found == ["S01: W01 is over the weekly hours limit (50 h, limit 48 h)"]


# ---------------------------------------------------------------------------- the stand-ins' failure modes, end to end

async def test_an_infeasible_solver_loops_through_compliance_and_writes_nothing(monkeypatch):
    tools = canned()
    tools["solve"] = FakeTool("solve", R.SOLVE_INFEASIBLE)
    patch_tools(monkeypatch, tools)
    out = await supervisor.ainvoke({})
    assert out["rounds"] == 3 and not out["compliant"] and not out.get("published")
    assert out["breaches"] == ["the solver returned no roster"]
    assert len(tools["solve"].calls) == 12  # 3 rounds x max_iter 4
    assert not tools["schedules"].calls and not tools["shift_confirm"].calls and not tools["notify"].calls


async def test_no_training_records_fail_compliance(monkeypatch):
    tools = canned()
    tools["training_currency"] = FakeTool("training_currency", R.TRAINING_CURRENCY_EMPTY)
    patch_tools(monkeypatch, tools)
    out = await supervisor.ainvoke({"only_site": "S01"})
    assert out["rounds"] == 3 and not out.get("published")
    assert out["breaches"][0] == "S01: W01 has no current qualification" and len(out["breaches"]) == 5


async def test_no_policy_rules_fail_compliance_with_a_reason(monkeypatch):
    tools = canned()
    tools["rules"] = FakeTool("rules", R.POLICY_RULES_EMPTY)
    patch_tools(monkeypatch, tools)
    out = await supervisor.ainvoke({})
    assert out["rounds"] == 3 and not out.get("published")
    assert out["breaches"] == ["the policy service returned no rules, so the roster cannot be checked"]


async def test_w5_an_empty_mes_answer_still_publishes(monkeypatch):
    """Deliberate weakness W5: no lines from MES reads as every line down; the run publishes anyway."""
    tools = canned()
    tools["line_availability"] = FakeTool("line_availability", R.LINE_AVAILABILITY_EMPTY)
    patch_tools(monkeypatch, tools)
    out = await supervisor.ainvoke({})
    assert all(d["headcount"] == 0 for d in out["demand"].values())
    assert out["published"] and out["compliant"] and len(tools["shift_confirm"].calls[0]["shifts"]) == 14
    assert "Deliberate weakness W5" in pathlib.Path("agents/forecast_demand.py").read_text()


# --------------------------------------------------------------------------------------------- writeback

async def test_writeback_retries_a_timeout_twice(monkeypatch):
    tools = canned()
    tools["schedules"] = FakeTool("schedules", R.SCHEDULES_OK,
                                  fail=[ToolException("Workday did not answer within 10 s")] * 2)
    patch_tools(monkeypatch, tools)
    assert (await writeback.writeback({"sites": ["S01"], "roster": []}))["published"] is True
    assert len(tools["schedules"].calls) == 3


async def test_writeback_gives_up_after_three_timeouts_and_does_not_retry_other_errors(monkeypatch):
    tools = canned()
    tools["schedules"] = FakeTool("schedules", {}, fail=[httpx.ReadTimeout("slow")] * 5)
    patch_tools(monkeypatch, tools)
    assert (await writeback.writeback({"sites": ["S01"], "roster": []}))["published"] is False
    assert len(tools["schedules"].calls) == 3
    tools["schedules"] = FakeTool("schedules", {}, fail=[ToolException("Workday answered HTTP 400")])
    patch_tools(monkeypatch, tools)
    with pytest.raises(ToolException):
        await writeback.writeback({"sites": ["S01"], "roster": []})


async def test_w4_a_timeout_on_the_last_write_repeats_the_ones_that_succeeded(monkeypatch):
    tools = canned()
    tools["notify"] = FakeTool("notify", R.NOTIFY_ACCEPTED, fail=[ToolException("Microsoft Teams did not answer within 10 s")])
    patch_tools(monkeypatch, tools)
    assert (await writeback.writeback({"sites": ["S01"], "roster": []}))["published"] is True
    assert len(tools["schedules"].calls) == 2 and len(tools["shift_confirm"].calls) == 2  # sent twice
    src = pathlib.Path("agents/writeback.py").read_text()
    assert "Deliberate weakness W4" in src and "for _ in range(3):" in src


async def test_writeback_with_no_sites_writes_nothing(monkeypatch):
    tools = canned()
    patch_tools(monkeypatch, tools)
    assert (await writeback.writeback({"sites": [], "roster": []}))["published"] is False
    assert not tools["schedules"].calls and not tools["notify"].calls


async def test_a_one_site_run_writes_only_that_site(monkeypatch):
    tools = canned()
    patch_tools(monkeypatch, tools)
    out = await supervisor.ainvoke({"only_site": "S07"})
    assert out["published"] and out["sites"] == ["S07"]
    assert [s["site_id"] for s in tools["shift_confirm"].calls[0]["shifts"]] == ["S07"]
    assert [s["site_id"] for s in tools["schedules"].calls[0]["roster"]["sites"]] == ["S07"]


# --------------------------------------------------------------------------------------------- copilot

async def test_copilot_answers_from_the_roster_store_without_its_age(monkeypatch):
    patch_tools(monkeypatch, canned())
    out = await copilot.ainvoke({"question": "Who is on the early shift at S04?"})
    assert out["site"] == "S04" and out["answer"] == "On S04 the roster is: early shift on S04-L1: W01, W02, W03, W04, W05."
    assert out["answer_ok"] is True
    assert "2026-11-20" not in out["answer"] and "generated" not in out["answer"]  # W3
    assert describe({}) == "There is no roster for that site."


@pytest.mark.parametrize("question,site", [
    ("Who is on shift at S04?", "S04"), ("who works at s4", "S04"), ("Who is at site-04?", "S04"),
    ("roster for site 4 please", "S04"), ("Site-12 tomorrow?", "S12"),
    ("Who is on shift tomorrow?", ""), ("What about site-100?", ""), ("And S100?", ""),
])
def test_site_in_question(question, site):
    assert site_in(question) == site


async def test_copilot_asks_which_site_and_has_no_roster_for_an_unknown_one(monkeypatch):
    patch_tools(monkeypatch, canned())
    out = await copilot.ainvoke({"question": "Who is on shift tomorrow?"})
    assert out["answer"] == "Which site do you mean? Ask about one of S01 to S14."
    out = await copilot.ainvoke({"question": "Who is at S20?"})
    assert out["site"] == "S20" and out["answer"] == "There is no roster for that site."


@pytest.mark.parametrize("spec,at,open_", [
    ("07:00-19:00", "2026-11-20 08:30", True), ("07:00-19:00", "2026-11-20 06:59", False),
    ("07:00-19:00", "2026-11-20 19:00", False), ("00:00-24:00", "2026-11-20 03:00", True),
    ("22:00-06:00", "2026-11-20 23:30", True), ("22:00-06:00", "2026-11-20 12:00", False),
    ("07:00-24:00", "2026-11-20 23:59", True), ("07:00-24:00", "2026-11-20 06:59", False),
    ("00:00-06:00", "2026-11-20 05:59", True),
])
def test_business_hours(monkeypatch, spec, at, open_):
    monkeypatch.setenv("COPILOT_HOURS", spec)
    monkeypatch.setenv("COPILOT_TZ", "Europe/London")
    now = datetime.strptime(at, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Europe/London"))
    assert hours.is_open(now) is open_


def test_business_hours_wording_and_bad_setting(monkeypatch):
    monkeypatch.delenv("COPILOT_HOURS", raising=False)
    assert hours.describe() == "between 07:00 and 19:00 (Europe/London)"
    monkeypatch.setenv("COPILOT_HOURS", "00:00-24:00")
    assert hours.describe() == "always"
    monkeypatch.setenv("COPILOT_HOURS", "nine to five")
    with pytest.raises(ValueError):
        hours.is_open()


@pytest.mark.parametrize("spec", ["24:00-06:00", "07:00-24:30", "7:00-19:00", "07:00-25:00"])
def test_bad_business_hours_are_refused(monkeypatch, spec):
    monkeypatch.setenv("COPILOT_HOURS", spec)
    with pytest.raises(ValueError):
        hours.window()


def test_unknown_time_zone_is_refused(monkeypatch):
    monkeypatch.setenv("COPILOT_HOURS", "07:00-19:00")
    monkeypatch.setenv("COPILOT_TZ", "Mars/Base")
    with pytest.raises(Exception):
        hours.window()


# ------------------------------------------------------------------------------------------ the model

def test_model_factory(monkeypatch):
    for k in ("WPO_LLM", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT"):
        monkeypatch.delenv(k, raising=False)
    assert isinstance(llm.chat_model(), llm.OfflineAnswers)  # auto, no keys: offline
    monkeypatch.setenv("WPO_LLM", "azure")
    with pytest.raises(RuntimeError, match="needs AZURE_OPENAI_ENDPOINT"):
        llm.chat_model()  # insisting on Azure without keys is an error, not a silent fallback
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.invalid")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "not-a-real-key")
    model = llm.chat_model()
    assert type(model).__name__ == "AzureChatOpenAI" and model.deployment_name == "gpt-4o-mini"
    monkeypatch.setenv("WPO_LLM", "auto")
    assert type(llm.chat_model()).__name__ == "AzureChatOpenAI"  # auto with an endpoint and key (Compose, a sandbox)
    monkeypatch.setenv("WPO_LLM", "offline")
    assert isinstance(llm.chat_model(), llm.OfflineAnswers)
    assert llm.OfflineAnswers().invoke("anything").content == R.CHAT_COMPLETION["choices"][0]["message"]["content"]


def test_verdict():
    assert llm.verdict('{"ok": true}') is True and llm.verdict('{"ok": false}') is False
    assert llm.verdict("Looks fine to me.") is None and llm.verdict('{"ok": "yes"}') is None
    assert llm.verdict("[true]") is None and llm.verdict(None) is None


async def test_the_model_answers_through_the_llm_stand_in(monkeypatch):
    """What Compose does: the agents' Azure OpenAI client pointed at the LLM stand-in. Here the client's requests go
    in-process to the stand-in's own app (the OpenAI SDK sends through httpx2, which respx does not see)."""
    import httpx2

    from stubs.stub_llm import app as stand_in
    monkeypatch.setenv("WPO_LLM", "auto")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "http://stub-llm:8000")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "stub-no-key")
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    paths: list[str] = []

    async def seen(request):
        paths.append(request.url.path)
    built = llm.AzureChatOpenAI
    in_process = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=stand_in), event_hooks={"request": [seen]})
    monkeypatch.setattr("agents.llm.AzureChatOpenAI", lambda **kw: built(**kw, http_async_client=in_process))
    reply = await llm.chat_model().ainvoke("Check this.")
    assert paths == ["/openai/deployments/gpt-4o-mini/chat/completions"]
    assert llm.verdict(reply.content) is True and reply.response_metadata["model_name"] == "gpt-4o-mini"


def test_azure_client_does_not_retry_by_itself(monkeypatch):
    monkeypatch.setenv("WPO_LLM", "azure")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.invalid")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "not-a-real-key")
    assert llm.chat_model().max_retries == 0  # otherwise the SDK honours Retry-After before W1 sees the 429


# ------------------------------------------------------------------------------------------ isolation, MCP results

def test_agents_never_call_a_stand_in_directly():
    for f in pathlib.Path("agents").glob("*.py"):
        text = f.read_text()
        for host in ("stub-sap", "stub-workday", "stub-mes", "stub-lms", "stub-cuopt", "stub-teams", "stub-policy",
                     "stub-roster-store", "stub-llm", ":8000", "stub_responses"):
            assert host not in text, f"{f.name} mentions {host}"
        assert "httpx.get(" not in text and "httpx.post(" not in text and "requests." not in text, f.name


def test_reading_tool_results():
    from agents.mcp_client import data
    from .fakes import blocks
    assert data(blocks(R.PRODUCTION_PLAN)) == R.PRODUCTION_PLAN
    assert data(blocks({})) == {} and data([]) is None
    assert data('{"status": "ok"}') == {"status": "ok"}  # a plain string
    assert data((blocks(R.SOLVE_OK), None)) == R.SOLVE_OK  # a (content, artifact) pair


def test_tool_errors_are_raised_not_returned_as_text():
    """The adapter's default hands a tool's error text back as if it were the answer; then W1 never retries and a
    run with SAP down 'succeeds'. The client must be built with handle_tool_errors=False."""
    from agents.mcp_client import client
    assert client.handle_tool_errors is False


@pytest.mark.parametrize("leaf,expect", [
    (httpx.ReadTimeout("slow"), "MCP server workday did not answer"),
    (httpx.ConnectError("refused"), "MCP server workday could not be reached (ConnectError)"),
    (ConnectionRefusedError(), "MCP server workday could not be reached (ConnectionRefusedError)"),
])
def test_a_failing_mcp_server_becomes_a_tool_error(leaf, expect):
    from agents.mcp_client import as_tool_error
    group = BaseExceptionGroup("unhandled errors in a TaskGroup", [ExceptionGroup("inner", [leaf])])
    err = as_tool_error(group, "MCP server workday")
    assert isinstance(err, ToolException) and str(err) == expect
    assert writeback.timed_out(err) is ("did not answer" in expect)  # writeback retries timeouts only


async def test_the_tool_wrapper_turns_transport_failures_into_tool_errors():
    from agents.mcp_client import Tool

    class Down:
        name = "absences"

        async def ainvoke(self, args):
            raise BaseExceptionGroup("unhandled errors in a TaskGroup", [httpx.ConnectError("refused")])

    class Failing:
        name = "absences"

        async def ainvoke(self, args):
            raise ToolException("Workday answered HTTP 429 (Retry-After: 60 s)")

    with pytest.raises(ToolException, match="MCP server workday could not be reached"):
        await Tool(Down(), "workday").ainvoke({})
    with pytest.raises(ToolException, match="Workday answered HTTP 429"):
        await Tool(Failing(), "workday").ainvoke({})
