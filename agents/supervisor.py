"""The nightly roster: a LangGraph supervisor over nodes 1-4, in order. Compliance "fail" loops back to the optimizer."""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .compliance import compliance, route_compliance
from .forecast_demand import forecast_demand
from .optimize_roster import optimize_roster
from .writeback import writeback


class RosterState(TypedDict, total=False):
    only_site: str
    sites: list[str]
    demand: dict
    forecast_note: str
    forecast_ok: bool | None
    roster: list[dict]
    hours: dict
    solver_status: str
    compliant: bool
    breaches: list[str]
    rounds: int
    published: bool


builder = StateGraph(RosterState)
builder.add_node("forecast_demand", forecast_demand)
builder.add_node("optimize_roster", optimize_roster)
builder.add_node("compliance", compliance)
builder.add_node("writeback", writeback)
builder.add_edge(START, "forecast_demand")
builder.add_edge("forecast_demand", "optimize_roster")
builder.add_edge("optimize_roster", "compliance")
builder.add_conditional_edges("compliance", route_compliance, {"pass": "writeback", "fail": "optimize_roster", "stop": END})
builder.add_edge("writeback", END)
supervisor = builder.compile()
