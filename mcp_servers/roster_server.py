"""MCP server in front of stub-roster-store (the roster store: the last published roster).

Deliberate weakness W3 (see README): it hands out the last published roster with its generated_at, but the copilot
does not pass the age on, so after a bad night managers are answered from yesterday's roster.
"""
import os

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from mcp_servers._common import TIMEOUT_S, answer, stand_in

mcp = FastMCP("roster", host="0.0.0.0", port=9000, stateless_http=True, json_response=True)
ROSTER_URL = os.getenv("ROSTER_URL", "http://stub-roster-store:8000")


def for_site(published: dict, site: str) -> dict:
    """One site's part of the published roster, with the roster's id, time and status; empty when the site has none."""
    shifts = [s for s in published.get("sites", []) if s.get("site_id") == site]
    if not shifts:
        return {}
    return {"roster_id": published.get("roster_id"), "generated_at": published.get("generated_at"),
            "status": published.get("status"), "site_id": site, "shifts": shifts}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
def store(site: str) -> dict:
    """The last roster published for a site (empty when there is none)."""
    with stand_in("Roster store"):
        published = answer(httpx.get(f"{ROSTER_URL}/roster", timeout=TIMEOUT_S))
    return for_site(published, site)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
