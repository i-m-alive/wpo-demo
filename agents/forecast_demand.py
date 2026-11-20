"""Node 1 · forecast_demand: staffing demand per site and line, from SAP's production plan, MES line availability and
Workday absences, with Azure OpenAI writing the reasoning a planner reads."""
from __future__ import annotations

import asyncio

import httpx
from langchain_core.tools import ToolException
from openai import RateLimitError

from .llm import llm
from .mcp_client import items, tools_named

FIXED_DELAY_S = 1  # seconds, the same every time
SHIFTS_PER_LINE = 2


def demand_per_site(sites: list[str], lines: list[dict], absences: list[dict]) -> dict:
    """Shifts to staff per site: two per running line, and how many people are already off that day."""
    out = {}
    for site in sites:
        running = [x["line"] for x in lines if x["site"] == site and x["status"] == "running"]
        out[site] = {"lines": running, "shifts": len(running) * SHIFTS_PER_LINE,
                     "absent": sum(1 for a in absences if a["site"] == site)}
    return out


def summary(demand: dict) -> str:
    """One line per site, as a planner would read it."""
    parts = []
    for site, d in demand.items():
        lines = ", ".join(d["lines"]) or "no running line"
        absent = f", {d['absent']} absent" if d["absent"] else ""
        parts.append(f"{site}: {d['shifts']} shifts on {lines}{absent}")
    return "Demand " + "; ".join(parts) + "."


async def forecast_demand(state: dict) -> dict:
    # ---------------------------------------------------------------------------------------------------------
    # DELIBERATE DEFECT W1 (demo 1) - DO NOT FIX.
    # When Workday, SAP or MES fails (for example Workday throttling with HTTP 429), or the model is rate limited,
    # this retries forever, after the same fixed one-second wait every time, and never reads Retry-After. Under a
    # throttle that multiplies the calls to the throttled system. It is the weakness the first NaviStorm demo finds;
    # the fix (honour Retry-After, cap at 3 attempts, add jitter) is what the demo recommends. Leave it as it is.
    # ---------------------------------------------------------------------------------------------------------
    while True:
        try:
            tools = await tools_named("sap.production_plan", "mes.line_availability", "workday.absences")
            sites = items(await tools["production_plan"].ainvoke({}))
            if state.get("only_site"):
                sites = [s for s in sites if s == state["only_site"]]
            lines = items(await tools["line_availability"].ainvoke({}))
            absences = items(await tools["absences"].ainvoke({}))
            demand = demand_per_site(sites, lines, absences)
            note = await llm.ainvoke("Explain tonight's staffing demand for a production planner.\n"
                                     f"DRAFT: {summary(demand)}")
            return {"sites": sites, "demand": demand, "forecast_note": note.content}
        except (ToolException, RateLimitError, httpx.HTTPError):
            await asyncio.sleep(FIXED_DELAY_S)
