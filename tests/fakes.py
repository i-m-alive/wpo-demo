"""Stand-ins for MCP tools, used by the agent tests through monkeypatch. Plain objects with a name and an `ainvoke`:
nothing here is an MCP server, client or agent, so a NaviStorm scan of the repo is the same with or without tests/."""
from __future__ import annotations

import json

from mcp_servers.roster_server import for_site
from stubs import stub_responses as R


def blocks(value) -> list[dict]:
    """What a real MCP tool hands LangChain (checked against the running servers): the object the tool returned, as
    one JSON text block."""
    return [{"type": "text", "text": json.dumps(value, indent=2)}]


class FakeTool:
    def __init__(self, name: str, answer=None, fail: list | None = None):
        self.name, self.answer, self.fail, self.calls = name, answer, list(fail or []), []

    async def ainvoke(self, args: dict):
        self.calls.append(args)
        if self.fail:
            raise self.fail.pop(0)
        value = self.answer(args) if callable(self.answer) else self.answer
        return blocks(value)


def canned() -> dict[str, FakeTool]:
    """Every tool, answering like the real servers do with the canned answers of stubs/stub_responses.py."""
    return {
        "production_plan": FakeTool("production_plan", R.PRODUCTION_PLAN),
        "line_availability": FakeTool("line_availability", R.LINE_AVAILABILITY),
        "absences": FakeTool("absences", R.ABSENCES),
        "workers": FakeTool("workers", R.WORKERS),
        "training_currency": FakeTool("training_currency", R.TRAINING_CURRENCY),
        "solve": FakeTool("solve", R.SOLVE_OK),
        "rules": FakeTool("rules", R.POLICY_RULES),
        "schedules": FakeTool("schedules", R.SCHEDULES_OK),
        "shift_confirm": FakeTool("shift_confirm", R.SHIFT_CONFIRM_OK),
        "notify": FakeTool("notify", R.NOTIFY_ACCEPTED),
        "store": FakeTool("store", lambda a: for_site(R.ROSTER_STORE_GET, a["site"])),
    }


def patch_tools(monkeypatch, tools: dict[str, FakeTool]) -> list[tuple[str, ...]]:
    """Replaces tools_named in every agent module; returns the names each node asked for, in order."""
    asked: list[tuple[str, ...]] = []

    async def fake(*names: str) -> dict:
        asked.append(names)
        return {n.split(".", 1)[1]: tools[n.split(".", 1)[1]] for n in names}

    for mod in ("forecast_demand", "optimize_roster", "compliance", "writeback", "manager_copilot"):
        monkeypatch.setattr(f"agents.{mod}.tools_named", fake)
    return asked
