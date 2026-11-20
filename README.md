# wpo-reference

A small, realistic Workforce Optimization (WPO) product for NaviStorm to draw and, later, to break. NaviStorm is a
fault-injection tool; this repo is the system it injects faults into. **Nothing here talks to a real system.**

- Six FastAPI stand-ins with canned answers: SAP S/4, Workday, MES, the learning system, NVIDIA cuOpt, Microsoft Teams.
- One MCP server in front of each, plus `policy` and `roster`: 8 servers, 11 tools; the three write tools are marked
  `destructiveHint: true`.
- LangGraph agents that reach those systems **only through MCP**: a supervisor graph running
  `forecast_demand → optimize_roster → compliance → writeback` (compliance "fail" loops back to the optimizer), and
  `manager_copilot`, a separate graph with its own entry point and business hours.
- One Docker image, one Compose file: `make up` starts all 15 services. Only the agents (port 8080) are published, and
  only on this machine (127.0.0.1).

No latency benchmarking, no load generation, no performance measurement: that is not this repo's job.

## Run it

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
make test     # 83 unit and API tests: no Docker, no network, no keys
make up       # builds and starts everything; agents on http://localhost:8080
curl -X POST localhost:8080/roster/run  -H 'content-type: application/json' -d '{}'
curl -X POST localhost:8080/copilot/ask -H 'content-type: application/json' -d '{"question":"Who is on shift at site-04?"}'
make down
make smoke    # all of the above in one go, checked, on port 18080, cleaned up afterwards
```

`POST /roster/run` takes `{}` for all 14 sites or `{"site": "site-07"}` for one, and answers how many sites were
rostered, whether the roster was published, how many compliance rounds it took, and the forecast in words. A site that
is not in the production plan answers 404; a system that fails in a way the agents do not retry (e.g. Teams refusing a
notification) answers 502 with the system named. The copilot asks "Which site do you mean?" when the question names none.

Every failure of a stand-in or an MCP server reaches the agents as an error (`agents/mcp_client.py`), so their retry
rules apply: forecast_demand retries it forever (W1), writeback retries timeouts.

## What is in it

| Folder | What |
|---|---|
| `data/` | The canned answers, hard-coded JSON: 14 sites, 56 workers, 12 absences, 28 production lines, 84 training records, 4 policy rules, last night's roster |
| `stubs/` | The six stand-ins (`stub_sap.py` …), each a few lines of FastAPI |
| `mcp_servers/` | The eight MCP servers, one file each; a failing or slow stand-in becomes an MCP tool error |
| `agents/` | `mcp_client.py` (the only way out: `tools_named("workday.absences", …)`), `llm.py`, the five agents, `supervisor.py`, `manager_copilot.py`, `hours.py`, `main.py` (the API) |
| `tests/` | Unit and API tests. **Rule:** they never define agents, MCP servers or clients of their own, so NaviStorm scans the same topology with or without them |
| `scripts/` | `smoke.sh` (Docker end to end), `check_topology.py` (scans this repo with NaviStorm's scanner and compares with `expected-topology.json`) |
| `expected-topology.json` | What NaviStorm must draw: the answer key |
| `docs/` | The implementation plan, `screens/` from a real NaviStorm run |

### The agents

| Node | MCP tools | Model | Retry, as the brief asks |
|---|---|---|---|
| `forecast_demand` | `sap.production_plan`, `mes.line_availability`, `workday.absences` | Azure OpenAI | **unbounded, fixed 1 s, ignores Retry-After** (W1, deliberate) |
| `optimize_roster` | `workday.workers`, `lms.training_currency`, `cuopt.solve` | — | 2 retries (3 attempts), max 4 iterations |
| `compliance` | `policy.rules`, `lms.training_currency` | — | none; "pass" → writeback, "fail" → optimizer, at most 3 rounds |
| `writeback` | `workday.schedules`, `sap.shift_confirm`, `teams.notify` | — | 2 retries on a timeout (the write path) |
| `manager_copilot` | `roster.store` | Azure OpenAI | none; business hours |

## Deliberate weaknesses: do not fix

They are what the NaviStorm demos find. Each is marked in the code.

| # | Where | What |
|---|---|---|
| W1 | `agents/forecast_demand.py` | Retries forever after the same 1 s wait and never reads Retry-After. Under a Workday throttle (HTTP 429) it multiplies the calls to Workday. The demo's recommended fix: honour Retry-After, cap at 3 attempts, add jitter |
| W2 | `agents/optimize_roster.py` | One solve for all 14 sites, so the optimizer waits for every forecast: one slow site holds up all of them |
| W3 | `agents/manager_copilot.py`, `mcp_servers/roster_server.py` | The copilot answers from the last published roster without saying how old it is: after a bad night, managers get yesterday's roster as if it were today's |
| W4 | `agents/writeback.py` | A timeout on any one write repeats all of them, so writes that already succeeded are sent again (duplicate schedules and shift confirmations: the "duplicate write" fault on the journey wireframe) |

## Settings (`.env`, see `.env.example`)

| Variable | Default | Meaning |
|---|---|---|
| `WPO_LLM` | `auto` | `auto`: Azure OpenAI when `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_API_KEY` are set, otherwise an offline model with fixed answers. `offline` / `azure` force one |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT` | empty, empty, `gpt-4o` | Only for a real Azure OpenAI deployment. Never commit `.env` |
| `COPILOT_HOURS`, `COPILOT_TZ` | `00:00-24:00` in Compose (07:00-19:00 in code), `Europe/London` | The copilot's business hours; outside them it answers 423 |
| `WPO_FORCE_COMPLIANCE_FAIL` | `0` | `1` makes compliance fail, to show the loop back to the optimizer (3 rounds, then the run stops) |
| `AGENTS_PORT` | `8080` | The port the agents are published on |

## What NaviStorm shows

Pointed at this folder, with nothing configured by hand (no `navistorm.yaml`), NaviStorm's Topology reads
**1 orchestrator, 5 agents, 11 MCP tools, 6 systems, 18 edges** (plus the compliance loop and 9 tool → system links),
and every node and edge says what classified it: code, MCP tool manifests, Docker Compose, vendor fingerprints, and after
a sandbox run, OTel traces. See [DEMO.md](DEMO.md) for the walkthrough and `docs/screens/` for the screens.

Check it without the console:

```bash
NAVISTORM_BACKEND=~/Desktop/NaviStorm/backend ~/Desktop/NaviStorm/backend/.venv/bin/python scripts/check_topology.py
```

**NaviStorm version needed: branch `wpo-demo`** (`m4-experiments` plus the fixes below). Check the checkout you run:
`git merge-base --is-ancestor 3cb5a00 HEAD && echo "fixes present"`. With `CHAOS_ENABLED=0` its console shows only
onboarding, topology and the sandbox, like `main`; `main` itself cannot read this repo. Building this repo found two
NaviStorm gaps (commits `a3d8542` and `3cb5a00`, narrowed after code review in `466771c`):

1. A LangGraph node defined in its own module and calling the model through a helper was also listed as a file
   NaviStorm "could not read".
2. A Compose service with both `build: .` and `image:` was treated as a stock image, so the sandbox plan left all 15
   services out.

Without them the topology is still right, but Check shows one "could not read" note and the runtime plan is empty.

## Decisions (accepted 20 Nov 2026)

| # | Decision |
|---|---|
| WD1 | Its own folder and git repo, local; pushed only when asked |
| WD2 | Follow the team brief: MCP only, no Service Bus queue or roster writes from the optimizer and compliance (the journey wireframe has them; a later variant can add them) |
| WD3 | Agent names from the brief (`forecast_demand` …) |
| WD4 | A fixed-order LangGraph `StateGraph`, compiled as `supervisor` (not a model-routed supervisor) |
| WD5 | One Compose file, one image, 15 services |
| WD6 | Azure OpenAI when configured, an offline model otherwise (setting `auto`); the topology is the same either way |
| WD7 | Each node calls its tools in code, then asks the model to reason over the results, so every run exercises every tool |
| WD8 | Weaknesses W2 and W3 as well as W1 |
| WD9 | Business hours enforced in code, "always open" in Compose so a demo works at any hour |
| WD10 | The compliance loop stops after 3 rounds |
