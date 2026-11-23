"""Node 4 · writeback: the write path. The roster to Workday, the staffed shifts back to SAP (one call for every site),
a note to managers in Teams. Retries on a timeout (twice)."""
from __future__ import annotations

import httpx
from langchain_core.tools import ToolException

from .mcp_client import tools_named


def timed_out(exc: Exception) -> bool:
    return isinstance(exc, httpx.TimeoutException) or "did not answer" in str(exc)


async def writeback(state: dict) -> dict:
    if not state.get("sites"):
        return {"published": False}  # nothing to publish (e.g. a site that is not in the production plan)
    tools = await tools_named("workday.schedules", "sap.shift_confirm", "teams.notify")
    roster = state.get("roster", [])
    # Deliberate weakness W4 (see README): a timeout on any one write repeats all of them, so writes that already
    # succeeded are sent again (duplicate schedules and shift confirmations). Leave it as it is.
    for _ in range(3):
        try:
            await tools["schedules"].ainvoke({"roster": {"sites": roster}})
            await tools["shift_confirm"].ainvoke({"shifts": roster})
            await tools["notify"].ainvoke({"payload": {"text": f"Roster published for {len(state['sites'])} sites"}})
            return {"published": True}
        except (httpx.TimeoutException, ToolException) as exc:
            if not timed_out(exc):
                raise
            continue
    return {"published": False}
