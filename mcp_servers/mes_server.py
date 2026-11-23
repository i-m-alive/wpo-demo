"""MCP server in front of stub-mes (manufacturing execution system)."""
import os

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from mcp_servers._common import TIMEOUT_S, answer, stand_in

mcp = FastMCP("mes", host="0.0.0.0", port=9000, stateless_http=True, json_response=True)
MES_URL = os.getenv("MES_URL", "http://stub-mes:8000")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
def line_availability() -> dict:
    """Which lines are running, and any maintenance window."""
    with stand_in("MES"):
        return answer(httpx.get(f"{MES_URL}/line_availability", timeout=TIMEOUT_S))


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
