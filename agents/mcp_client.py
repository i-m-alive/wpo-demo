"""The agents' only way to reach a system: MCP. One client knows the eight MCP servers; `tools_named` hands a node the
tools it uses, by their full names ("workday.absences"). Nothing in agents/ calls a stand-in's HTTP endpoint.

Every failure reaches the agents as a ToolException, so their retry rules see it:
  * a tool that reports an error (its stand-in failed or timed out): handle_tool_errors=False makes the adapter raise
    it instead of handing the error text back as if it were the answer;
  * an MCP server that is down or hangs: the client raises an ExceptionGroup, turned here into a ToolException that
    says "did not answer" for a timeout (writeback retries those) or "could not be reached" otherwise.
"""
from __future__ import annotations

import json
import os

import httpx
from langchain_core.tools import ToolException
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({
    "sap": {"url": os.getenv("SAP_MCP_URL", "http://mcp-sap:9000/mcp"), "transport": "streamable_http"},
    "workday": {"url": os.getenv("WORKDAY_MCP_URL", "http://mcp-workday:9000/mcp"), "transport": "streamable_http"},
    "mes": {"url": os.getenv("MES_MCP_URL", "http://mcp-mes:9000/mcp"), "transport": "streamable_http"},
    "lms": {"url": os.getenv("LMS_MCP_URL", "http://mcp-lms:9000/mcp"), "transport": "streamable_http"},
    "cuopt": {"url": os.getenv("CUOPT_MCP_URL", "http://mcp-cuopt:9000/mcp"), "transport": "streamable_http"},
    "teams": {"url": os.getenv("TEAMS_MCP_URL", "http://mcp-teams:9000/mcp"), "transport": "streamable_http"},
    "policy": {"url": os.getenv("POLICY_MCP_URL", "http://mcp-policy:9000/mcp"), "transport": "streamable_http"},
    "roster": {"url": os.getenv("ROSTER_MCP_URL", "http://mcp-roster:9000/mcp"), "transport": "streamable_http"},
}, handle_tool_errors=False)


def _leaves(exc: BaseException):
    if isinstance(exc, BaseExceptionGroup):
        for e in exc.exceptions:
            yield from _leaves(e)
    else:
        yield exc


def as_tool_error(exc: BaseException, what: str) -> ToolException:
    """A transport failure (often an ExceptionGroup from the MCP client) as one ToolException."""
    leaves = list(_leaves(exc))
    if any(isinstance(e, (httpx.TimeoutException, TimeoutError)) for e in leaves):
        return ToolException(f"{what} did not answer")
    first = next((e for e in leaves if not isinstance(e, ToolException)), leaves[0] if leaves else exc)
    if isinstance(first, ToolException):
        return first
    return ToolException(f"{what} could not be reached ({type(first).__name__})")


class Tool:
    """An MCP tool as the agents use it: `await tool.ainvoke(args)`, failing only with ToolException."""

    def __init__(self, tool, server: str):
        self._tool, self.name, self.server = tool, tool.name, server

    async def ainvoke(self, args: dict):
        try:
            return await self._tool.ainvoke(args)
        except ToolException:
            raise
        except (BaseExceptionGroup, httpx.HTTPError, OSError) as exc:
            raise as_tool_error(exc, f"MCP server {self.server}") from exc


async def tools_named(*names: str) -> dict:
    """The MCP tools with these full names ("server.tool"), keyed by tool name. Only the servers named are asked."""
    wanted: dict[str, set[str]] = {}
    for n in names:
        server, tool = n.split(".", 1)
        wanted.setdefault(server, set()).add(tool)
    found = {}
    for server, tools in wanted.items():
        try:
            offered = await client.get_tools(server_name=server)
        except (BaseExceptionGroup, httpx.HTTPError, OSError) as exc:
            raise as_tool_error(exc, f"MCP server {server}") from exc
        for t in offered:
            if t.name in tools:
                found[t.name] = Tool(t, server)
    missing = {n for n in names if n.split(".", 1)[1] not in found}
    if missing:
        raise LookupError(f"MCP tools not offered: {', '.join(sorted(missing))}")
    return found


def _texts(result) -> list[str]:
    """The text blocks of an MCP tool result, as LangChain hands it over (a list of content blocks, a plain string, or
    a (content, artifact) pair)."""
    if isinstance(result, tuple):
        result = result[0]
    if isinstance(result, str):
        return [result]
    return [b.get("text", "") if isinstance(b, dict) else getattr(b, "text", str(b)) for b in result or []]


def data(result):
    """A tool result as the JSON object its stand-in answered. Every tool answers one object (reads come in an
    envelope such as {"as_of": ..., "sites": [...]}), which MCP sends as one JSON text block."""
    texts = _texts(result)
    return json.loads(texts[0]) if texts else None
