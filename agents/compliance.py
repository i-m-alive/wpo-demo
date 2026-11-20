"""Node 3 · compliance: checks the candidate roster against the policy rules and training currency. No retry.
"pass" goes on to writeback, "fail" goes back to the optimizer (at most MAX_ROUNDS times, then the run stops)."""
from __future__ import annotations

import os

from .mcp_client import items, tools_named

MAX_ROUNDS = 3


def breaches(roster: dict, rules: list[dict], current: set[tuple[str, str]], hours: dict[str, float]) -> list[str]:
    """Rules the roster breaks. The solver stand-in answers an empty roster, which breaks none."""
    out = []
    limits = {r["id"]: r.get("limit") for r in rules}
    for site, shifts in (roster or {}).items():
        seen: set[str] = set()
        for shift in shifts or []:
            for w in shift.get("workers", []):
                if (w, shift.get("line")) not in current and "current_training" in limits:
                    out.append(f"{site}: {w} has no current training for {shift.get('line')}")
                if w in seen and limits.get("one_shift_per_day"):
                    out.append(f"{site}: {w} has two shifts")
                seen.add(w)
                if hours.get(w, 0) > (limits.get("max_weekly_hours") or 1e9):
                    out.append(f"{site}: {w} is over the weekly hours limit")
    return out


async def compliance(state: dict) -> dict:
    tools = await tools_named("policy.rules", "lms.training_currency")
    rules = items(await tools["rules"].ainvoke({}))
    current = {(t["worker_id"], t["line"]) for t in items(await tools["training_currency"].ainvoke({})) if t["current"]}
    found = breaches(state.get("roster", {}), rules, current, state.get("hours", {}))
    if os.getenv("WPO_FORCE_COMPLIANCE_FAIL") == "1":  # to show the loop back to the optimizer in a demo
        found.append("forced by WPO_FORCE_COMPLIANCE_FAIL")
    return {"compliant": not found and bool(rules), "breaches": found, "rounds": state.get("rounds", 0) + 1}


def route_compliance(state: dict) -> str:
    if state.get("compliant"):
        return "pass"
    return "stop" if state.get("rounds", 0) >= MAX_ROUNDS else "fail"
