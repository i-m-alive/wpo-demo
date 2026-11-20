"""MCP server in front of stub-teams (Microsoft Teams)."""
import os

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from mcp_servers._common import TIMEOUT_S, answer, stand_in

mcp = FastMCP("teams", host="0.0.0.0", port=9000, stateless_http=True, json_response=True)
TEAMS_URL = os.getenv("TEAMS_URL", "http://stub-teams:8000")


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
def notify(payload: dict) -> dict:
    """Tells managers the roster is live."""
    with stand_in("Microsoft Teams"):
        return answer(httpx.post(f"{TEAMS_URL}/notify", json=payload, timeout=TIMEOUT_S))


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
