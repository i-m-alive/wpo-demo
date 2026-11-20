"""Shared pieces of the MCP servers: errors from a stand-in become MCP tool errors, and canned data for the two
internal servers (policy, roster).

Each server keeps its own literal FastMCP(...) line, tool annotations and stand-in calls, so a reader (and NaviStorm)
sees in one file which tools it offers, which of them write, and which system each one reaches.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from functools import cache
from pathlib import Path

import httpx
from mcp.server.fastmcp.exceptions import ToolError

TIMEOUT_S = 10.0  # how long a tool waits for its stand-in
DATA = Path(__file__).resolve().parent.parent / "data"


@contextmanager
def stand_in(system: str):
    """Turns a stand-in that fails, refuses or times out into an MCP tool error (never a crash of the server)."""
    try:
        yield
    except httpx.TimeoutException as exc:
        raise ToolError(f"{system} did not answer within {TIMEOUT_S:g} s") from exc
    except httpx.HTTPStatusError as exc:
        raise ToolError(f"{system} answered HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise ToolError(f"{system} could not be reached ({type(exc).__name__})") from exc


def answer(r: httpx.Response):
    r.raise_for_status()
    return r.json()


@cache
def load(name: str):
    return json.loads((DATA / f"{name}.json").read_text())
