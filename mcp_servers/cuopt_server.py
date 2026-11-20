"""MCP server in front of stub-cuopt (NVIDIA cuOpt)."""
import os

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from mcp_servers._common import TIMEOUT_S, answer, stand_in

mcp = FastMCP("cuopt", host="0.0.0.0", port=9000, stateless_http=True, json_response=True)
CUOPT_URL = os.getenv("CUOPT_URL", "http://stub-cuopt:8000")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def solve(payload: dict) -> dict:
    """The optimisation itself: workers, training and demand in, a roster out. Changes nothing."""
    with stand_in("NVIDIA cuOpt"):
        return answer(httpx.post(f"{CUOPT_URL}/solve", json=payload, timeout=TIMEOUT_S))


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
