"""MCP server in front of stub-lms (learning system)."""
import os

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from mcp_servers._common import TIMEOUT_S, answer, stand_in

mcp = FastMCP("lms", host="0.0.0.0", port=9000, stateless_http=True, json_response=True)
LMS_URL = os.getenv("LMS_URL", "http://stub-lms:8000")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
def training_currency() -> list[dict]:
    """Who is qualified for which line today."""
    with stand_in("Learning system"):
        return answer(httpx.get(f"{LMS_URL}/training_currency", timeout=TIMEOUT_S))


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
