"""MCP server in front of stub-policy (the roster policy service: working-time, rest and skill rules)."""
import os

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from mcp_servers._common import TIMEOUT_S, answer, stand_in

mcp = FastMCP("policy", host="0.0.0.0", port=9000, stateless_http=True, json_response=True)
POLICY_URL = os.getenv("POLICY_URL", "http://stub-policy:8000")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
def rules() -> dict:
    """Working time, rest and skill rules every roster must keep."""
    with stand_in("Policy service"):
        return answer(httpx.get(f"{POLICY_URL}/rules", timeout=TIMEOUT_S))


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
