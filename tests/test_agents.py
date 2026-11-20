"""The agents: which tools each node uses, the retry behaviour the brief asks for (exactly), the compliance loop, the
copilot, business hours, the model factory, and that agents reach systems only through MCP."""
import pathlib
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
from langchain_core.tools import ToolException
from openai import RateLimitError

from agents import compliance, forecast_demand, hours, llm, optimize_roster, writeback
from agents.manager_copilot import copilot, describe
from agents.supervisor import supervisor

from .fakes import FakeTool, canned, patch_tools


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
    await copilot.ainvoke({"question": "Who works at site-02?"})
    assert asked == [
        ("sap.production_plan", "mes.line_availability", "workday.absences"),
        ("workday.workers", "lms.training_currency", "cuopt.solve"),
        ("policy.rules", "lms.training_currency"),
        ("workday.schedules", "sap.shift_confirm", "teams.notify"),
        ("roster.store",),
    ]
    assert out["published"] and out["compliant"] and len(out["sites"]) == 14


async def test_every_one_of_the_11_tools_is_called(monkeypatch):
    tools = canned()
    patch_tools(monkeypatch, tools)
    await supervisor.ainvoke({})
    await copilot.ainvoke({"question": "site-05"})
    assert all(t.calls for t in tools.values()), [n for n, t in tools.items() if not t.calls]
    assert len(tools["shift_confirm"].calls) == 14  # one confirmation per site


# --------------------------------------------------------------------------------- W1: the deliberate defect

async def test_forecast_retries_forever_with_a_fixed_delay(monkeypatch, sleeps):
    tools = canned()
    tools["absences"] = FakeTool("absences", [], fail=[ToolException("Workday answered HTTP 429")] * 50)
    patch_tools(monkeypatch, tools)
    out = await forecast_demand.forecast_demand({})
    assert len(sleeps) == 50 and set(sleeps) == {1.0}  # no cap, no back-off
    assert len(out["sites"]) == 14


async def test_forecast_ignores_retry_after(monkeypatch, sleeps):
    tools = canned()
    patch_tools(monkeypatch, tools)

    calls = {"n": 0}

    class Throttled:
        async def ainvoke(self, prompt):
            calls["n"] += 1
            if calls["n"] <= 3:
                raise rate_limited("30")
            return type("R", (), {"content": "ok"})()
    monkeypatch.setattr("agents.forecast_demand.llm", Throttled())
    await forecast_demand.forecast_demand({})
    assert sleeps == [1.0, 1.0, 1.0]  # Retry-After said 30 s; it waited 1 s each time


def test_the_defect_is_marked_and_still_unbounded():
    src = pathlib.Path("agents/forecast_demand.py").read_text()
    assert "DELIBERATE DEFECT W1" in src and "DO NOT FIX" in src
    assert "while True:" in src and "retry_after" not in src.lower().replace("retry-after", "")


async def test_forecast_for_one_site(monkeypatch):
    patch_tools(monkeypatch, canned())
    out = await forecast_demand.forecast_demand({"only_site": "site-03"})
    assert out["sites"] == ["site-03"] and out["demand"]["site-03"]["shifts"] == 2  # line-B is in maintenance
    assert out["forecast_note"].startswith("Demand site-03: 2 shifts on line-A")


# ------------------------------------------------------------------------------------------- the optimizer

async def test_optimizer_gives_up_after_three_attempts(monkeypatch):
    tools = canned()
    tools["solve"] = FakeTool("solve", {}, fail=[ToolException("cuOpt answered HTTP 500")] * 10)
    patch_tools(monkeypatch, tools)
    with pytest.raises(ToolException):
        await optimize_roster.optimize_roster({})
    assert len(tools["solve"].calls) == 3  # MAX_RETRIES = 2


async def test_optimizer_stops_after_max_iter(monkeypatch):
    tools = canned()
    tools["solve"] = FakeTool("solve", {"status": "PENDING"})
    patch_tools(monkeypatch, tools)
    out = await optimize_roster.optimize_roster({})
    assert len(tools["solve"].calls) == 4 and out["solver_status"] == "no answer after max_iter"


async def test_optimizer_solves_all_sites_at_once(monkeypatch):
    tools = canned()
    patch_tools(monkeypatch, tools)
    await optimize_roster.optimize_roster({"demand": {"site-01": {}, "site-02": {}}})
    (payload,) = [c["payload"] for c in tools["solve"].calls]
    assert set(payload["demand"]) == {"site-01", "site-02"}  # W2: one solve for every site
    assert all(t["current"] for t in payload["training"])


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
    rules = [{"id": "current_training"}, {"id": "one_shift_per_day", "limit": 1}, {"id": "max_weekly_hours", "limit": 48}]
    roster = {"site-01": [{"line": "line-A", "workers": ["w001", "w001"]}]}
    found = compliance.breaches(roster, rules, {("w001", "line-A")}, {"w001": 50})
    assert "site-01: w001 has two shifts" in found and any("weekly hours" in f for f in found)
    assert compliance.breaches({}, rules, set(), {}) == []
    assert compliance.route_compliance({"compliant": True}) == "pass"
    assert compliance.route_compliance({"compliant": False, "rounds": 1}) == "fail"
    assert compliance.route_compliance({"compliant": False, "rounds": 3}) == "stop"


# --------------------------------------------------------------------------------------------- writeback

async def test_writeback_retries_a_timeout_twice(monkeypatch):
    tools = canned()
    tools["schedules"] = FakeTool("schedules", {"status": "ok"}, fail=[ToolException("Workday did not answer within 10 s")] * 2)
    patch_tools(monkeypatch, tools)
    assert (await writeback.writeback({"sites": ["site-01"], "roster": {}}))["published"] is True
    assert len(tools["schedules"].calls) == 3


async def test_writeback_gives_up_after_three_timeouts_and_does_not_retry_other_errors(monkeypatch):
    tools = canned()
    tools["schedules"] = FakeTool("schedules", {}, fail=[httpx.ReadTimeout("slow")] * 5)
    patch_tools(monkeypatch, tools)
    assert (await writeback.writeback({"sites": [], "roster": {}}))["published"] is False
    assert len(tools["schedules"].calls) == 3
    tools["schedules"] = FakeTool("schedules", {}, fail=[ToolException("Workday answered HTTP 400")])
    patch_tools(monkeypatch, tools)
    with pytest.raises(ToolException):
        await writeback.writeback({"sites": [], "roster": {}})


# --------------------------------------------------------------------------------------------- copilot

async def test_copilot_answers_from_the_roster_store_without_its_age(monkeypatch):
    patch_tools(monkeypatch, canned())
    out = await copilot.ainvoke({"question": "Who is on the early shift at site-04?"})
    assert out["site"] == "site-04" and out["answer"].startswith("On site-04 the roster is: early shift on line-A")
    assert "2026-11-19" not in out["answer"] and "published" not in out["answer"]  # W3
    assert describe({}) == "There is no roster for that site."


@pytest.mark.parametrize("spec,at,open_", [
    ("07:00-19:00", "2026-11-20 08:30", True), ("07:00-19:00", "2026-11-20 06:59", False),
    ("07:00-19:00", "2026-11-20 19:00", False), ("00:00-24:00", "2026-11-20 03:00", True),
    ("22:00-06:00", "2026-11-20 23:30", True), ("22:00-06:00", "2026-11-20 12:00", False),
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


# ------------------------------------------------------------------------------------------ model, isolation

def test_model_factory(monkeypatch):
    for k in ("WPO_LLM", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert isinstance(llm.chat_model(), llm.OfflineAnswers)  # auto, no keys: offline
    monkeypatch.setenv("WPO_LLM", "azure")
    with pytest.raises(RuntimeError, match="needs AZURE_OPENAI_ENDPOINT"):
        llm.chat_model()  # insisting on Azure without keys is an error, not a silent fallback
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.invalid")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "not-a-real-key")
    assert type(llm.chat_model()).__name__ == "AzureChatOpenAI"
    monkeypatch.setenv("WPO_LLM", "auto")
    assert type(llm.chat_model()).__name__ == "AzureChatOpenAI"  # auto with keys (and in a NaviStorm sandbox run)
    monkeypatch.setenv("WPO_LLM", "offline")
    assert isinstance(llm.chat_model(), llm.OfflineAnswers)
    assert llm.OfflineAnswers().invoke("question\nDRAFT: the answer").content == "the answer"


def test_agents_never_call_a_stand_in_directly():
    for f in pathlib.Path("agents").glob("*.py"):
        text = f.read_text()
        for host in ("stub-sap", "stub-workday", "stub-mes", "stub-lms", "stub-cuopt", "stub-teams", ":8000"):
            assert host not in text, f"{f.name} mentions {host}"
        assert "httpx.get(" not in text and "httpx.post(" not in text and "requests." not in text, f.name


# ------------------------------------------------------------------------- reading MCP results (as MCP sends them)

def test_reading_list_and_object_results():
    from agents.mcp_client import data, items
    from .fakes import blocks
    assert items(blocks(["site-01", "site-02"])) == ["site-01", "site-02"]  # strings arrive unquoted, one per block
    assert items(blocks(["site-01"])) == ["site-01"]  # a one-item list stays a list
    assert items(blocks([])) == [] and items([]) == []
    assert items(blocks([{"id": "w001"}, {"id": "w002"}])) == [{"id": "w001"}, {"id": "w002"}]
    assert items('[{"id": "w001"}]') == [{"id": "w001"}]  # one block holding a JSON array
    assert data(blocks({"status": "ok"})) == {"status": "ok"} and data([]) is None
    assert data((blocks({"status": "OK", "roster": {}}), None)) == {"status": "OK", "roster": {}}  # (content, artifact)
