"""MCP server for the roster store: the last published roster per site. Internal: no system behind it.

Deliberate weakness W3 (see README): it hands out the last published roster without saying how old it is in a way the
copilot passes on, so after a bad night managers are answered from yesterday's roster.
"""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from mcp_servers._common import load

mcp = FastMCP("roster", host="0.0.0.0", port=9000, stateless_http=True, json_response=True)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
def store(site: str) -> dict:
    """The last roster published for a site (empty when there is none)."""
    return next((r for r in load("roster_published") if r["site"] == site), {})


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
