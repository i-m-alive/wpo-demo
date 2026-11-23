"""Node 1 · forecast_demand: staffing demand per site, from SAP's production plan, MES line availability and Workday
absences, with Azure OpenAI checking the forecast before it goes on."""
from __future__ import annotations

import asyncio

import httpx
from langchain_core.tools import ToolException
from openai import APIError, RateLimitError

from .llm import CHECK, llm, verdict
from .mcp_client import data, tools_named

FIXED_DELAY_S = 1  # seconds, the same every time


def demand_per_site(plan: list[dict], lines: list[dict], absences: list[dict]) -> dict:
    """People to roster per site: the headcount its planned line needs when MES reports that line running, none when
    it does not, and how many of the site's people are absent.

    Deliberate weakness W5 (see README): a line MES does not report counts as not running, so an empty answer from MES
    (HTTP 200, no lines) reads as "every line is down" rather than as a failure. Demand drops to zero, yet the run goes
    on and publishes a roster built on no line data. Leave it as it is."""
    running = {x["line_id"] for x in lines if x.get("status") == "RUNNING"}
    out = {}
    for p in plan:
        up = p["line_id"] in running
        out[p["site_id"]] = {"line": p["line_id"], "shift": p["shift"], "running": up,
                             "headcount": p["headcount_required"] if up else 0,
                             "absent": sum(1 for a in absences if a["site_id"] == p["site_id"])}
    return out


def summary(demand: dict) -> str:
    """One line per site, as a planner would read it."""
    parts = []
    for site, d in demand.items():
        need = f"{d['headcount']} people on {d['line']}, {d['shift'].lower()} shift" if d["running"] \
            else f"{d['line']} not running, no one needed"
        absent = f", {d['absent']} absent" if d["absent"] else ""
        parts.append(f"{site}: {need}{absent}")
    return "Demand " + "; ".join(parts) + "."


async def forecast_demand(state: dict) -> dict:
    # ---------------------------------------------------------------------------------------------------------
    # DELIBERATE DEFECT W1 (demo 1) - DO NOT FIX.
    # When Workday, SAP or MES fails (for example Workday throttling with HTTP 429), or the model fails or is limited,
    # this retries forever, after the same fixed one-second wait every time, and never reads Retry-After. Under a
    # throttle that multiplies the calls to the throttled system. It is the weakness the first NaviStorm demo finds;
    # the fix (honour Retry-After, cap at 3 attempts, add jitter) is what the demo recommends. Leave it as it is.
    # ---------------------------------------------------------------------------------------------------------
    while True:
        try:
            tools = await tools_named("sap.production_plan", "mes.line_availability", "workday.absences")
            plan = data(await tools["production_plan"].ainvoke({}))["sites"]
            if state.get("only_site"):
                plan = [p for p in plan if p["site_id"] == state["only_site"]]
            lines = data(await tools["line_availability"].ainvoke({}))["lines"]
            absences = data(await tools["absences"].ainvoke({}))["absences"]
            demand = demand_per_site(plan, lines, absences)
            draft = summary(demand)
            check = await llm.ainvoke(f"Check tonight's staffing forecast for a production planner. {CHECK}\n"
                                      f"FORECAST: {draft}")
            return {"sites": [p["site_id"] for p in plan], "demand": demand, "forecast_note": draft,
                    "forecast_ok": verdict(check.content)}
        except (ToolException, RateLimitError, APIError, httpx.HTTPError):
            await asyncio.sleep(FIXED_DELAY_S)
