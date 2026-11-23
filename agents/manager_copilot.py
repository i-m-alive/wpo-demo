"""The manager copilot: a separate graph with its own entry point, open in business hours (agents/hours.py). It reads
the roster store, answers in plain words, and has Azure OpenAI check the answer."""
from __future__ import annotations

import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .llm import CHECK, llm, verdict
from .mcp_client import data, tools_named

# A site as managers write it: "S04", "s4", "site-04", "site 4". Not "S100" or "site-100".
SITE = re.compile(r"\b(?:S|site[- ]?)(\d{1,2})\b", re.IGNORECASE)


class CopilotState(TypedDict, total=False):
    question: str
    site: str
    answer: str
    answer_ok: bool | None


def site_in(question: str) -> str:
    """The first site the question names, as the systems write it ("S04"); empty when it names none."""
    m = SITE.search(question or "")
    return f"S{int(m.group(1)):02d}" if m else ""


def describe(roster: dict) -> str:
    # Deliberate weakness W3 (see README): the answer never says when this roster was published, so after a bad
    # night a manager is told yesterday's roster as if it were today's. Leave it as it is.
    if not roster:
        return "There is no roster for that site."
    parts = [f"{s['shift'].lower()} shift on {s['line_id']}: {', '.join(s['assigned'])}" for s in roster.get("shifts", [])]
    return f"On {roster['site_id']} the roster is: " + "; ".join(parts) + "."


async def manager_copilot(state: CopilotState) -> CopilotState:
    site = state.get("site") or site_in(state.get("question", ""))
    if not site:
        return {"site": "", "answer": "Which site do you mean? Ask about one of S01 to S14.", "answer_ok": None}
    tools = await tools_named("roster.store")
    roster = data(await tools["store"].ainvoke({"site": site}))
    answer = describe(roster)
    check = await llm.ainvoke(f"Check an answer to a line manager's question against the roster. {CHECK}\n"
                              f"QUESTION: {state.get('question', '')}\nANSWER: {answer}")
    return {"site": site, "answer": answer, "answer_ok": verdict(check.content)}


g = StateGraph(CopilotState)
g.add_node("manager_copilot", manager_copilot)
g.add_edge(START, "manager_copilot")
g.add_edge("manager_copilot", END)
copilot = g.compile()
