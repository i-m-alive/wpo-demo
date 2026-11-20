"""The manager copilot: a separate graph with its own entry point, open in business hours (agents/hours.py). It reads
the roster store and answers in plain words with Azure OpenAI."""
from __future__ import annotations

import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .llm import llm
from .mcp_client import data, tools_named

SITE = re.compile(r"site-\d{2}")


class CopilotState(TypedDict, total=False):
    question: str
    site: str
    answer: str


def describe(roster: dict) -> str:
    # Deliberate weakness W3 (see README): the answer never says when this roster was published, so after a bad
    # night a manager is told yesterday's roster as if it were today's. Leave it as it is.
    if not roster:
        return "There is no roster for that site."
    parts = [f"{s['shift']} shift on {s['line']}: {', '.join(s['workers'])}" for s in roster.get("shifts", [])]
    return f"On {roster['site']} the roster is: " + "; ".join(parts) + "."


async def manager_copilot(state: CopilotState) -> CopilotState:
    site = state.get("site") or next(iter(SITE.findall(state.get("question", ""))), "site-01")
    tools = await tools_named("roster.store")
    roster = data(await tools["store"].ainvoke({"site": site}))
    reply = await llm.ainvoke(f"Answer the line manager's question: {state.get('question', '')}\nDRAFT: {describe(roster)}")
    return {"site": site, "answer": reply.content}


g = StateGraph(CopilotState)
g.add_node("manager_copilot", manager_copilot)
g.add_edge(START, "manager_copilot")
g.add_edge("manager_copilot", END)
copilot = g.compile()
