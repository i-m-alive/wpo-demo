"""Shared pieces of the MCP servers: errors from a stand-in become MCP tool errors.

Each server keeps its own literal FastMCP(...) line, tool annotations and stand-in calls, so a reader (and NaviStorm)
sees in one file which tools it offers, which of them write, and which system each one reaches.
"""
from __future__ import annotations

from contextlib import contextmanager

import httpx
from mcp.server.fastmcp.exceptions import ToolError

TIMEOUT_S = 10.0  # how long a tool waits for its stand-in


@contextmanager
def stand_in(system: str):
    """Turns a stand-in that fails, refuses or times out into an MCP tool error (never a crash of the server).
    A refusal that says when to come back (HTTP 429 with Retry-After) passes that on in the error, so the agent has
    what it needs to wait the right time, whether or not it does."""
    try:
        yield
    except httpx.TimeoutException as exc:
        raise ToolError(f"{system} did not answer within {TIMEOUT_S:g} s") from exc
    except httpx.HTTPStatusError as exc:
        wait = exc.response.headers.get("Retry-After")
        raise ToolError(f"{system} answered HTTP {exc.response.status_code}"
                        + (f" (Retry-After: {wait} s)" if wait else "")) from exc
    except httpx.HTTPError as exc:
        raise ToolError(f"{system} could not be reached ({type(exc).__name__})") from exc


def answer(r: httpx.Response):
    r.raise_for_status()
    return r.json()
