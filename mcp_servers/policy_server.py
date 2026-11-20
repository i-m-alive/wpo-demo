"""MCP server for the roster policy: working-time, rest and training rules. Internal: no system behind it."""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from mcp_servers._common import load

mcp = FastMCP("policy", host="0.0.0.0", port=9000, stateless_http=True, json_response=True)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
def rules() -> list[dict]:
    """Working time, rest and training rules every roster must keep."""
    return load("policy_rules")


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
