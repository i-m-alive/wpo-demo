"""MCP server in front of stub-sap (SAP S/4)."""
import os

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from mcp_servers._common import TIMEOUT_S, answer, stand_in

mcp = FastMCP("sap", host="0.0.0.0", port=9000, stateless_http=True, json_response=True)
SAP_URL = os.getenv("SAP_URL", "http://stub-sap:8000")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
def production_plan() -> list[str]:
    """Planned production: the ids of the sites that need a roster."""
    with stand_in("SAP S/4"):
        return answer(httpx.get(f"{SAP_URL}/production_plan", timeout=TIMEOUT_S))


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
def shift_confirm(site: str, shifts: list[dict]) -> dict:
    """Confirms a site's staffed shifts back to production planning."""
    with stand_in("SAP S/4"):
        return answer(httpx.post(f"{SAP_URL}/shift_confirm", json={"site": site, "shifts": shifts}, timeout=TIMEOUT_S))


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
