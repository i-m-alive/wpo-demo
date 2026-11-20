"""The agents' only way to reach a system: MCP. One client knows the eight MCP servers; `tools_named` hands a node the
tools it uses, by their full names ("workday.absences"). Nothing in agents/ calls a stand-in's HTTP endpoint."""
from __future__ import annotations

import json
import os

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
})


async def tools_named(*names: str) -> dict:
    """The MCP tools with these full names ("server.tool"), keyed by tool name. Only the servers named are asked."""
    wanted: dict[str, set[str]] = {}
    for n in names:
        server, tool = n.split(".", 1)
        wanted.setdefault(server, set()).add(tool)
    found = {}
    for server, tools in wanted.items():
        for t in await client.get_tools(server_name=server):
            if t.name in tools:
                found[t.name] = t
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


def _parse(text: str):
    try:
        return json.loads(text)
    except ValueError:
        return text  # a plain string item ("site-01")


def data(result):
    """A tool result that is one JSON object (solve, store, the write tools' {"status": "ok"})."""
    texts = _texts(result)
    return _parse(texts[0]) if texts else None


def items(result) -> list:
    """A tool result that is a list. MCP sends one text block per item (strings unquoted, objects as JSON); a single
    block holding a JSON array is read as that array."""
    texts = _texts(result)
    if len(texts) == 1:
        one = _parse(texts[0])
        return one if isinstance(one, list) else [one]
    return [_parse(t) for t in texts]
