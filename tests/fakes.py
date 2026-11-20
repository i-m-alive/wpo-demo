"""Stand-ins for MCP tools, used by the agent tests through monkeypatch. Plain objects with a name and an `ainvoke`:
nothing here is an MCP server, client or agent, so a NaviStorm scan of the repo is the same with or without tests/."""
from __future__ import annotations

import json

from stubs._common import load


def blocks(value) -> list[dict]:
    """What a real MCP tool hands LangChain (checked against the running servers): a list arrives as one text block
    per item, strings unquoted and objects as JSON; one object arrives as one JSON text block."""
    if isinstance(value, list):
        return [{"type": "text", "text": v if isinstance(v, str) else json.dumps(v, indent=2)} for v in value]
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
    """Every tool, answering like the real servers do with the canned data."""
    roster = {r["site"]: r for r in load("roster_published")}
    return {
        "production_plan": FakeTool("production_plan", load("sites")),
        "line_availability": FakeTool("line_availability", load("line_availability")),
        "absences": FakeTool("absences", load("absences")),
        "workers": FakeTool("workers", load("workers")),
        "training_currency": FakeTool("training_currency", load("training_currency")),
        "solve": FakeTool("solve", {"status": "OK", "roster": {}}),
        "rules": FakeTool("rules", load("policy_rules")),
        "schedules": FakeTool("schedules", {"status": "ok"}),
        "shift_confirm": FakeTool("shift_confirm", {"status": "ok"}),
        "notify": FakeTool("notify", {"status": "ok"}),
        "store": FakeTool("store", lambda a: roster.get(a["site"], {})),
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
