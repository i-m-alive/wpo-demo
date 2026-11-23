"""Node 3 · compliance: checks the candidate roster against the policy rules and training currency. No retry.
"pass" goes on to writeback, "fail" goes back to the optimizer (at most MAX_ROUNDS times, then the run stops)."""
from __future__ import annotations

import os

from .mcp_client import data, tools_named

MAX_ROUNDS = 3


def breaches(roster: list[dict], rules: list[dict], current: set[str], hours: dict[str, float]) -> list[str]:
    """Rules the roster breaks, worded for a planner.

    Only what one night's roster can show is checked: SKILL_REQUIRED (every assigned worker holds a current
    qualification) and MAX_HOURS_PER_WEEK (contract hours). MIN_REST_HOURS and MAX_CONSECUTIVE_DAYS need the shifts of
    earlier days, which no system here supplies, so they are not checked. No rules, or no roster, is a breach in
    itself: the roster cannot be shown to keep the policy."""
    if not rules:
        return ["the policy service returned no rules, so the roster cannot be checked"]
    if not roster:
        return ["the solver returned no roster"]
    value = {r["type"]: r.get("value") for r in rules}
    max_hours = value.get("MAX_HOURS_PER_WEEK")
    out = []
    for entry in roster:
        site = entry.get("site_id")
        for w in entry.get("assigned", []):
            if value.get("SKILL_REQUIRED") and w not in current:
                out.append(f"{site}: {w} has no current qualification")
            if max_hours is not None and hours.get(w, 0) > max_hours:
                out.append(f"{site}: {w} is over the weekly hours limit ({hours[w]:g} h, limit {max_hours} h)")
    return out


async def compliance(state: dict) -> dict:
    tools = await tools_named("policy.rules", "lms.training_currency")
    rules = data(await tools["rules"].ainvoke({}))["rules"]
    current = {q["worker_id"] for q in data(await tools["training_currency"].ainvoke({}))["qualifications"]
               if q["status"] == "CURRENT"}
    # a run with no sites (one that is not in the production plan) has nothing to check
    found = breaches(state.get("roster", []), rules, current, state.get("hours", {})) if state.get("sites") else []
    if os.getenv("WPO_FORCE_COMPLIANCE_FAIL") == "1":  # to show the loop back to the optimizer in a demo
        found.append("forced by WPO_FORCE_COMPLIANCE_FAIL")
    return {"compliant": not found, "breaches": found, "rounds": state.get("rounds", 0) + 1}


def route_compliance(state: dict) -> str:
    if state.get("compliant"):
        return "pass"
    return "stop" if state.get("rounds", 0) >= MAX_ROUNDS else "fail"
