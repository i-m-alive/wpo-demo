# wpo-reference

A small, realistic Workforce Optimization (WPO) product for NaviStorm to draw and, later, to break. NaviStorm is a
fault-injection tool; this repo is the system it injects faults into. **Nothing here talks to a real system.**

- Nine FastAPI stand-ins with canned answers, all hard-coded in [`stubs/stub_responses.py`](stubs/stub_responses.py):
  the six systems of the brief (SAP S/4, Workday, MES, the learning system, NVIDIA cuOpt, Microsoft Teams), the policy
  service, the roster store, and Azure OpenAI (`stub-llm`, no key needed). Five of them have a failure mode (a Workday
  throttle, empty results, an infeasible solve) that is switched on with one setting.
- One MCP server in front of each stand-in but the LLM: 8 servers, 11 tools; the three write tools are marked
  `destructiveHint: true`.
- LangGraph agents that reach those systems **only through MCP**: a supervisor graph running
  `forecast_demand → optimize_roster → compliance → writeback` (compliance "fail" loops back to the optimizer), and
  `manager_copilot`, a separate graph with its own entry point and business hours. The model is Azure OpenAI, reached
  through its own client (in Compose: the LLM stand-in).
- One Docker image, one Compose file: `make up` starts all 18 services. Only the agents (port 8080) are published, and
  only on this machine (127.0.0.1).

No latency benchmarking, no load generation, no performance measurement: that is not this repo's job. (`solver_time_ms`
in the canned solver answer is only a field: no stand-in ever waits.)

## Run it

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
make test     # 130 unit and API tests: no Docker, no network, no keys
make up       # builds and starts everything; agents on http://localhost:8080
curl -X POST localhost:8080/roster/run  -H 'content-type: application/json' -d '{}'
curl -X POST localhost:8080/copilot/ask -H 'content-type: application/json' -d '{"question":"Who is on shift at S04?"}'
make down
make smoke    # all of the above plus two failure modes, checked, on port 18080, cleaned up afterwards
```

`POST /roster/run` takes `{}` for all 14 sites or `{"site": "S07"}` for one, and answers how many sites were rostered,
whether the roster was published, how many compliance rounds it took and any breaches, the solver's status, the
forecast in words, and the model's check of it (`forecast_ok`). A site that is not in the production plan answers 404;
a system that fails in a way the agents do not retry (e.g. Teams refusing a notification) answers 502 with the system
named. The copilot answers with the site, the answer and the model's check (`answer_ok`); it understands "S04",
"site-04" and "site 4", and asks "Which site do you mean?" when the question names none.

Every failure of a stand-in or an MCP server reaches the agents as an error (`agents/mcp_client.py`), so their retry
rules apply: forecast_demand retries it forever (W1), writeback retries timeouts. A refusal with Retry-After keeps it in
the error ("Workday answered HTTP 429 (Retry-After: 60 s)"), so it is plain that the agent had it and ignored it.

## Failure modes

The canned answers of `stubs/stub_responses.py` include what a stand-in answers when something is wrong. Each is
switched on by one setting (Compose passes it to that stand-in; `.env.example` lists them) and changes nothing else:

```bash
make mode SYSTEM=workday MODE=throttle   # recreate only stub-workday, now throttled; MODE=normal switches it back
WORKDAY_MODE=throttle make up            # or start the whole stack with it
```

| Setting | The stand-in answers | What the run does |
|---|---|---|
| `WORKDAY_MODE=throttle` (`WORKDAY_RETRY_AFTER` 30, 60 or 120; 60 by default) | HTTP 429 `TOO_MANY_REQUESTS` with Retry-After, on every Workday route | **W1**: forecast_demand retries every second, forever, and never waits what Workday asked; `/roster/run` never answers (use `curl --max-time`). `docker compose logs stub-workday` shows the 429s pile up |
| `CUOPT_MODE=infeasible` | HTTP 200, `INFEASIBLE`, no roster | The optimizer tries max_iter (4) times, compliance fails ("the solver returned no roster"), back to the optimizer, 3 rounds, then the run stops: nothing written. The compliance loop from a real fault |
| `LMS_MODE=empty` | HTTP 200, no qualifications | Compliance fails (no one has a current qualification), 3 rounds, nothing written |
| `POLICY_MODE=empty` | HTTP 200, no rules | Compliance fails ("the policy service returned no rules…"), 3 rounds, nothing written |
| `MES_MODE=empty` | HTTP 200, no lines | **W5**: every line reads as down, demand drops to zero, and the roster is published anyway |

A mode the stand-in does not know (`MES_MODE=slow`) stops it at start-up rather than letting it answer normally.

## What is in it

| Folder | What |
|---|---|
| `stubs/` | `stub_responses.py`, every canned answer (as handed over by the team), and the nine stand-ins (`stub_sap.py` …), each a few lines of FastAPI. 14 sites (S01–S14), one line each, 10 workers (W01–W10), 2 absences, 4 policy rules, last night's roster |
| `mcp_servers/` | The eight MCP servers, one file each; a failing or slow stand-in becomes an MCP tool error |
| `agents/` | `mcp_client.py` (the only way out: `tools_named("workday.absences", …)`), `llm.py`, the five agents, `supervisor.py`, `manager_copilot.py`, `hours.py`, `main.py` (the API) |
| `tests/` | Unit and API tests. **Rule:** they never define agents, MCP servers or clients of their own, so NaviStorm scans the same topology with or without them |
| `scripts/` | `smoke.sh` (Docker end to end), `check_topology.py` (scans this repo with NaviStorm's scanner and compares with `expected-topology.json`) |
| `expected-topology.json` | What NaviStorm must draw: the answer key |
| `docs/` | The 20 Nov implementation plan, audit and test plan, and `screens/` from a NaviStorm run of that version (6 systems; see "What NaviStorm shows") |

### The agents

| Node | MCP tools | Model | Retry, as the brief asks |
|---|---|---|---|
| `forecast_demand` | `sap.production_plan`, `mes.line_availability`, `workday.absences` | Azure OpenAI | **unbounded, fixed 1 s, ignores Retry-After** (W1, deliberate) |
| `optimize_roster` | `workday.workers`, `lms.training_currency`, `cuopt.solve` | — | 2 retries (3 attempts), max 4 iterations |
| `compliance` | `policy.rules`, `lms.training_currency` | — | none; "pass" → writeback, "fail" → optimizer, at most 3 rounds |
| `writeback` | `workday.schedules`, `sap.shift_confirm`, `teams.notify` | — | 2 retries on a timeout (the write path) |
| `manager_copilot` | `roster.store` | Azure OpenAI | none; business hours |

The model checks rather than writes: forecast_demand and the copilot hand it their own draft and ask for `{"ok": true}`
or `{"ok": false}`, which is also the LLM stand-in's canned answer. The draft is what the API returns; the model's check
comes with it (`forecast_ok`, `answer_ok`).

Compliance checks what one night's roster can show: **SKILL_REQUIRED** (every assigned worker holds a current
qualification) and **MAX_HOURS_PER_WEEK** (contract hours). MIN_REST_HOURS and MAX_CONSECUTIVE_DAYS need earlier days'
shifts, which no system here supplies, so they are not checked. It also does not check that a worker is on one site
only or is not absent: the canned solver answer puts W01–W05 on all 14 sites and W03 is on leave, and checking either
would fail every run.

## Deliberate weaknesses: do not fix

They are what the NaviStorm demos find. Each is marked in the code.

| # | Where | What |
|---|---|---|
| W1 | `agents/forecast_demand.py` | Retries forever after the same 1 s wait and never reads Retry-After. Under a Workday throttle (HTTP 429, `WORKDAY_MODE=throttle`) it multiplies the calls to Workday. The demo's recommended fix: honour Retry-After, cap at 3 attempts, add jitter |
| W2 | `agents/optimize_roster.py` | One solve for all 14 sites, so the optimizer waits for every forecast: one slow site holds up all of them |
| W3 | `agents/manager_copilot.py`, `mcp_servers/roster_server.py` | The copilot answers from the last published roster without saying how old it is (the store says: `generated_at`): after a bad night, managers get yesterday's roster as if it were today's |
| W4 | `agents/writeback.py` | A timeout on any one write repeats all of them, so writes that already succeeded are sent again (duplicate schedules and shift confirmations: the "duplicate write" fault on the journey wireframe) |
| W5 | `agents/forecast_demand.py` | An empty answer from MES (HTTP 200, no lines, `MES_MODE=empty`) reads as "every line is down" rather than as a failure: demand drops to zero, yet the run publishes a roster built on no line data |

## Settings (`.env`, see `.env.example`)

| Variable | Default | Meaning |
|---|---|---|
| `WPO_LLM` | `auto` | `auto`: Azure OpenAI when `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_API_KEY` are set, otherwise an offline model with the same fixed answer. `offline` / `azure` force one |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT` | In Compose: `http://stub-llm:8000`, a dummy key, `gpt-4o-mini` | The LLM stand-in unless `.env` names a real Azure OpenAI deployment. Never commit `.env` |
| `WORKDAY_MODE`, `WORKDAY_RETRY_AFTER`, `MES_MODE`, `LMS_MODE`, `CUOPT_MODE`, `POLICY_MODE` | `normal`, `60` | The stand-ins' failure modes (above) |
| `COPILOT_HOURS`, `COPILOT_TZ` | `00:00-24:00` in Compose (07:00-19:00 in code), `Europe/London` | The copilot's business hours; outside them it answers 423 |
| `WPO_FORCE_COMPLIANCE_FAIL` | `0` | `1` makes compliance fail, to show the loop back to the optimizer (3 rounds, then the run stops) |
| `AGENTS_PORT` | `8080` | The port the agents are published on |

## What NaviStorm shows

Pointed at this folder, with nothing configured by hand (no `navistorm.yaml`), NaviStorm's Topology reads
**1 orchestrator, 5 agents, 11 MCP tools, 8 systems, 18 edges** (plus the compliance loop and 11 tool → system links),
and every node and edge says what classified it: code, MCP tool manifests, Docker Compose, vendor fingerprints, and after
a sandbox run, OTel traces. The 8 systems are the brief's six plus the policy service and the roster store: NaviStorm
does not know those two by name, so it names them after their hosts (`stub-policy`, `stub-roster-store`). The LLM
stand-in is the model's endpoint, not a system. See [DEMO.md](DEMO.md) for the walkthrough; the screens in
`docs/screens/` are from the 20 Nov version (6 systems, model gpt-4o).

Check it without the console:

```bash
NAVISTORM_BACKEND=~/Desktop/NaviStorm/backend ~/Desktop/NaviStorm/backend/.venv/bin/python scripts/check_topology.py
```

**NaviStorm version needed: a branch with the fixes below** (`wpo-demo`, i.e. `m4-experiments` plus the fixes, or a
later one; `m7-findings` passes every check). Check the checkout you run:
`git merge-base --is-ancestor 3cb5a00 HEAD && echo "fixes present"`. With `CHAOS_ENABLED=0` its console shows only
onboarding, topology and the sandbox, like `main`; `main` itself cannot read this repo. Building this repo found two
NaviStorm gaps (commits `a3d8542` and `3cb5a00`, narrowed after code review in `466771c`):

1. A LangGraph node defined in its own module and calling the model through a helper was also listed as a file
   NaviStorm "could not read".
2. A Compose service with both `build: .` and `image:` was treated as a stock image, so the sandbox plan left all the
   services out.

Without them the topology is still right, but Check shows one "could not read" note and the runtime plan is empty.

## Decisions

Accepted 20 Nov 2026:

| # | Decision |
|---|---|
| WD1 | Its own folder and git repo, local; pushed only when asked |
| WD2 | Follow the team brief: MCP only, no Service Bus queue or roster writes from the optimizer and compliance (the journey wireframe has them; a later variant can add them) |
| WD3 | Agent names from the brief (`forecast_demand` …) |
| WD4 | A fixed-order LangGraph `StateGraph`, compiled as `supervisor` (not a model-routed supervisor) |
| WD5 | One Compose file, one image (15 services then, 18 now) |
| WD6 | Azure OpenAI when configured, an offline model otherwise (setting `auto`); the topology is the same either way |
| WD7 | Each node calls its tools in code, then asks the model about the results, so every run exercises every tool |
| WD8 | Weaknesses W2 and W3 as well as W1 |
| WD9 | Business hours enforced in code, "always open" in Compose so a demo works at any hour |
| WD10 | The compliance loop stops after 3 rounds |

Taken 23 Nov 2026 when moving to the team's canned stub responses (defaults; WD12 and WD16 still need the team's OK):

| # | Decision |
|---|---|
| WD11 | Where the brief's table and `stub_responses.py` differ (the write answers, notify's 202, the solver's roster, the production plan as site records), the canned list wins |
| WD12 | The policy service and the roster store are HTTP stand-ins like the others, so faults can be injected into them; NaviStorm then draws 8 systems, not 6 |
| WD13 | The agents reach the LLM stand-in through the Azure OpenAI client (Compose sets its endpoint), not through MCP: the brief lists the model apart from the tools, and NaviStorm draws it from that client |
| WD14 | `POST /roster` is served by the roster store but not offered as an MCP tool: no node of the brief writes it (11 tools, 18 edges stay) |
| WD15 | Failure modes are switched by one setting per stand-in, read at start-up; no control route, so nothing new for NaviStorm to read |
| WD16 | An empty MES answer is left as weakness W5 rather than handled |
| WD17 | The model deployment is `gpt-4o-mini`, as the LLM stand-in answers, so code and traces name the same model |
