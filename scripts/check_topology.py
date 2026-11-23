"""Scans this repo with NaviStorm's own scanner and compares the result with expected-topology.json.

    NAVISTORM_BACKEND=~/path/to/NaviStorm/backend \
      ~/path/to/NaviStorm/backend/.venv/bin/python scripts/check_topology.py

Checks what the Topology screen will show, with nothing configured by hand: the counts (1 orchestrator, 5 agents,
11 MCP tools, 8 systems, 18 edges), every node and edge, the compliance loop, the triggers, the retry settings read from
the code, the write tools, and that every node and edge records which source classified it. Then scans a copy without
tests/ and scripts/ and checks the result is identical (test code must never change the topology).
Prints one line per check and exits 1 on the first difference.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = Path(os.path.expanduser(os.environ.get("NAVISTORM_BACKEND", "~/Desktop/NaviStorm/backend")))
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("NAVISTORM_ENV_FILE", "/nonexistent")

from navistorm.graph import sources  # noqa: E402
from navistorm.scanner.analyse import RepoInput, analyse  # noqa: E402

EXPECTED = json.loads((ROOT / "expected-topology.json").read_text())
failures = 0


def check(what: str, ok: bool, detail: str = "") -> None:
    global failures
    print(f"{'ok  ' if ok else 'FAIL'}  {what}" + (f": {detail}" if detail and not ok else ""))
    failures += not ok


def scan(root: Path):
    ex, _ = analyse([RepoInput("wpo-reference", root)], 2000, 1_000_000)
    return ex


def edges(ex, kinds) -> list[list[str]]:
    return sorted([e.kind, ex.name_of(e.src), ex.name_of(e.dst), e.rw] for e in ex.edges.values() if e.kind in kinds)


def summary(ex) -> dict:
    loops = {(ex.name_of(e.src), ex.name_of(e.dst)) for e in ex.edges.values() if e.attrs.get("loop")}
    return {
        "types": dict(Counter(n.type for n in ex.nodes.values())),
        "agent_level": [x for x in edges(ex, ("handoff", "calls", "uses_model")) if (x[1], x[2]) not in loops],
        "loops": sorted(["handoff", a, b, ""] for a, b in loops),
        "hits": edges(ex, ("hits",)),
        "unrecognised": ex.unrecognised,
    }


def main() -> int:
    print(f"NaviStorm scanner: {BACKEND}")
    ex = scan(ROOT)
    s = summary(ex)
    c = EXPECTED["counts"]
    t = s["types"]
    orch = [n for n in ex.nodes.values() if n.type == "pipeline" and n.attrs.get("role") != "entry"]
    check("1 orchestrator", len(orch) == c["orchestrators"] and orch[0].name == EXPECTED["orchestrator"],
          str([n.name for n in orch]))
    check("5 agents", sorted(n.name for n in ex.nodes.values() if n.type == "agent") == EXPECTED["agents"])
    check("11 MCP tools", sorted(n.name for n in ex.nodes.values() if n.type == "tool" and n.attrs.get("server"))
          == EXPECTED["mcp_tools"])
    check(f"{c['systems']} systems", sorted(n.name for n in ex.nodes.values() if n.type == "system") == EXPECTED["systems"])
    models = [n for n in ex.nodes.values() if n.type == "model"]
    check(f"1 model, {EXPECTED['model']['provider']} {EXPECTED['model']['model_id']}", len(models) == 1 and models[0].attrs.get("provider") == EXPECTED["model"]["provider"]
          and models[0].attrs.get("model_id") == EXPECTED["model"]["model_id"], str([(m.name, m.attrs) for m in models]))
    check("18 agent-level edges", s["agent_level"] == sorted(EXPECTED["agent_level_edges"]),
          f"missing {[x for x in EXPECTED['agent_level_edges'] if x not in s['agent_level']]}, "
          f"extra {[x for x in s['agent_level'] if x not in EXPECTED['agent_level_edges']]}")
    check("the compliance -> optimizer loop", s["loops"] == sorted(EXPECTED["loops"]), str(s["loops"]))
    check(f"{len(EXPECTED['tool_system_edges'])} tool -> system links with R/W", s["hits"] == sorted(EXPECTED["tool_system_edges"]), str(s["hits"]))
    other = [e for e in ex.edges.values() if e.kind not in ("handoff", "calls", "uses_model", "hits")]
    check("no other edges", not other, str([(e.kind, ex.name_of(e.src), ex.name_of(e.dst)) for e in other]))
    check("stages in order", orch and orch[0].attrs.get("stages") == EXPECTED["stages"])
    copilot = next((n for n in ex.nodes.values() if n.name == "manager_copilot"), None)
    check("triggers", orch and orch[0].attrs.get("triggers") == EXPECTED["triggers"]["supervisor"]
          and copilot is not None and copilot.attrs.get("entry_point") is True
          and copilot.attrs.get("triggers") == EXPECTED["triggers"]["manager_copilot"])
    writes = sorted(n.name for n in ex.nodes.values() if n.type == "tool" and n.attrs.get("rw_hint") == "W")
    check("write tools marked destructive", writes == EXPECTED["write_tools"], str(writes))
    check("nothing NaviStorm could not read", not s["unrecognised"], str(s["unrecognised"]))

    retry = {}
    for e in ex.edges.values():
        r = e.attrs.get("retry")
        if e.kind == "calls" and isinstance(r, dict):
            retry.setdefault(ex.name_of(e.src), r.get("text", ""))
    want = {"forecast_demand": "unbounded · fixed 1 s · ignores Retry-After",
            "optimize_roster": "2 retries (3 attempts)", "compliance": "no retry in code", "writeback": "2 retries (3 attempts)"}
    for node, text in want.items():
        check(f"retry on {node}: {retry.get(node, '?')}", retry.get(node, "").startswith(text))
    check("optimizer keeps max 4 iterations", "max 4 iterations" in retry.get("optimize_roster", ""))
    check("writeback retries on timeout", "TimeoutException" in retry.get("writeback", ""))

    ext: dict[str, list[str]] = {}
    for n in ex.nodes.values():
        ext[n.name] = [ev.extractor for ev in n.evidence]
    no_source = [n.name for n in ex.nodes.values() if not sources(ext[n.name], n.attrs, n.type)]
    check("every node records its source", not no_source, str(no_source))
    no_source_e = [(ex.name_of(e.src), ex.name_of(e.dst)) for e in ex.edges.values()
                   if not sources([ev.extractor for ev in e.evidence], e.attrs, ex.nodes[e.dst].type)]
    check("every edge records its source", not no_source_e, str(no_source_e))
    tools_manifest = [n.name for n in ex.nodes.values() if n.type == "tool"
                      and not any(x["key"] == "mcp_manifest" for x in sources(ext[n.name], n.attrs, n.type))]
    check("every MCP tool classified from its MCP manifest", not tools_manifest, str(tools_manifest))
    by_source = Counter(x["label"] for n in ex.nodes.values() for x in sources(ext[n.name], n.attrs, n.type))
    print(f"      sources on nodes: {dict(by_source)}")

    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "wpo-reference"
        shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", ".venv", "tests", "scripts", "__pycache__"))
        check("same topology without tests/ and scripts/", summary(scan(copy)) == s)

    print("all checks passed" if not failures else f"{failures} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
