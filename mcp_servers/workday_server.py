"""MCP server in front of stub-workday (Workday)."""
import os

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from mcp_servers._common import TIMEOUT_S, answer, stand_in

mcp = FastMCP("workday", host="0.0.0.0", port=9000, stateless_http=True, json_response=True)
WORKDAY_URL = os.getenv("WORKDAY_URL", "http://stub-workday:8000")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
def absences() -> dict:
    """Approved leave and sickness."""
    with stand_in("Workday"):
        return answer(httpx.get(f"{WORKDAY_URL}/absences", timeout=TIMEOUT_S))


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
def workers() -> dict:
    """Every worker: site, contract hours and skills."""
    with stand_in("Workday"):
        return answer(httpx.get(f"{WORKDAY_URL}/workers", timeout=TIMEOUT_S))


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
def schedules(roster: dict) -> dict:
    """Publishes the approved roster."""
    with stand_in("Workday"):
        return answer(httpx.post(f"{WORKDAY_URL}/schedules", json=roster, timeout=TIMEOUT_S))


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
