"""Node 4 · writeback: the write path. The roster to Workday, the staffed shifts back to SAP, a note to managers in
Teams. Retries on a timeout (twice)."""
from __future__ import annotations

import httpx
from langchain_core.tools import ToolException

from .mcp_client import tools_named


def timed_out(exc: Exception) -> bool:
    return isinstance(exc, httpx.TimeoutException) or "did not answer" in str(exc)


async def writeback(state: dict) -> dict:
    tools = await tools_named("workday.schedules", "sap.shift_confirm", "teams.notify")
    roster = state.get("roster", {})
    for _ in range(3):
        try:
            await tools["schedules"].ainvoke({"roster": roster})
            for site in state.get("sites", []):
                await tools["shift_confirm"].ainvoke({"site": site, "shifts": roster.get(site, [])})
            await tools["notify"].ainvoke({"payload": {"text": f"Roster published for {len(state.get('sites', []))} sites"}})
            return {"published": True}
        except (httpx.TimeoutException, ToolException) as exc:
            if not timed_out(exc):
                raise
            continue
    return {"published": False}
