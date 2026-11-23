"""MCP server in front of stub-sap (SAP S/4)."""
import os

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from mcp_servers._common import TIMEOUT_S, answer, stand_in

mcp = FastMCP("sap", host="0.0.0.0", port=9000, stateless_http=True, json_response=True)
SAP_URL = os.getenv("SAP_URL", "http://stub-sap:8000")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
def production_plan() -> dict:
    """Planned production per site: the line, the shift, the planned units and the headcount it needs."""
    with stand_in("SAP S/4"):
        return answer(httpx.get(f"{SAP_URL}/production_plan", timeout=TIMEOUT_S))


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
def shift_confirm(shifts: list[dict]) -> dict:
    """Confirms the staffed shifts of every site back to production planning, in one call."""
    with stand_in("SAP S/4"):
        return answer(httpx.post(f"{SAP_URL}/shift_confirm", json={"shifts": shifts}, timeout=TIMEOUT_S))


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
