# Demo: NaviStorm draws wpo-reference

A click-by-click walkthrough, about 17 minutes. **Part A** runs the WPO product on its own. **Part B** points NaviStorm
at it and shows the topology the team brief asks for. Screens from a real run of the 20 Nov version (6 systems) are in `docs/screens/`.

## Before you start

| Check | How | Expected |
|---|---|---|
| Docker Desktop is running | `docker info` | server details |
| This repo is set up | `python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`, then `make test` | `130 passed` |
| NaviStorm runs a branch with the fixes | in your NaviStorm folder: `git checkout wpo-demo` (or a later branch such as `m7-findings`), then `git merge-base --is-ancestor 3cb5a00 HEAD && echo "fixes present"` | `fixes present` (see README, "NaviStorm version needed") |
| NaviStorm's `backend/.env` | lines of their own | `CHAOS_ENABLED=1`, `RUNTIME_RUNNER=docker`, `ALLOW_LOCAL_REPOS=true` |

Start NaviStorm's API and console as usual (NaviStorm's M1 UI test guide, section 1.3), open the console and sign in.
With developer sign-in, tick every role.

## Part A · The product on its own (5 minutes)

| # | Do | You should see |
|---|---|---|
| A1 | `make up` | After about a minute, 18 services healthy (`docker compose ps`) |
| A2 | `curl -X POST localhost:8080/roster/run -H 'content-type: application/json' -d '{}'` | `"sites":14,"published":true,"compliant":true,"rounds":1`, the forecast in words: "Demand S01: 5 people on S01-L1, early shift, 1 absent; …" and `"forecast_ok":true` (the model's check, answered by the LLM stand-in) |
| A3 | `curl -X POST localhost:8080/copilot/ask -H 'content-type: application/json' -d '{"question":"Who is on shift at S04?"}'` | "On S04 the roster is: early shift on S04-L1: W01, W02, W03, W04, W05." (W3: nothing says the roster was generated on 20 Nov) |
| A4 | Show the defect: open `agents/forecast_demand.py` | The `DELIBERATE DEFECT W1 - DO NOT FIX` block above `while True` |
| A5 | Show the loop from a real fault: `make mode SYSTEM=cuopt MODE=infeasible`, then A2 again | `"published":false,"compliant":false,"rounds":3`, breach "the solver returned no roster", solver status "no answer after max_iter (INFEASIBLE)". Then `make mode SYSTEM=cuopt MODE=normal` |
| A6 | Show W1 live: `make mode SYSTEM=workday MODE=throttle`, then `curl --max-time 10 -X POST localhost:8080/roster/run -H 'content-type: application/json' -d '{}'` | No answer (cut off after 10 s). `docker compose logs stub-workday \| grep -c '" 429'` keeps climbing, about one a second, although each 429 said Retry-After: 60. Then `make down` (the agent would retry forever) |
| A7 | `make down` | Everything stopped and removed |

## Part B · NaviStorm (10 minutes)

### B1 · Add the product (nothing configured by hand)

| # | Do | You should see |
|---|---|---|
| B1.1 | **Products** → **+ New product**; *Product name* `Workforce Optimization (WPO)` | |
| B1.2 | *Repo URL or path*: the full path of this folder (run `pwd` in it), e.g. `/Users/<you>/Desktop/wpo-reference` | "✓ NaviStorm can read it" · "Folder on this machine" |
| B1.3 | **Scan** | "Scan complete", then the Check page |
| B1.4 | Check: no "could not read" note; confirm the cards (the three writes: `sap.shift_confirm`, `workday.schedules`, `teams.notify`) → **Go live** | "… is live" |

### B2 · Topology (`docs/screens/01-topology.png`)

| # | Look at | You should see |
|---|---|---|
| B2.1 | The header | "WPO agent topology · From … MCP tool manifests, vendor fingerprints, Docker Compose and code · **1 orchestrator, 5 agents, 11 MCP tools, 8 systems, 18 edges**"; below: "Also: 1 loop back to an earlier agent and 11 tool-to-system links" |
| B2.2 | The orchestrator strip | "supervisor (LangGraph) · runs forecast_demand → optimize_roster → compliance → writeback · loops back: compliance → optimize_roster when "fail" · started by POST /roster/run" |
| B2.3 | The three columns | WPO agents (5) in stage order with manager_copilot last; 11 MCP tools grouped by server (Workday 3, Sap 2, the others 1); Systems (8): NVIDIA cuOpt, Learning system, MES, SAP S/4, Microsoft Teams, Workday, and stub-policy and stub-roster-store (the policy service and roster store, named after their hosts) |
| B2.4 | Click `forecast_demand` → its edge to `mes.line_availability` (or `workday.absences`) | *Retry policy* **unbounded** · "Retry: unbounded · fixed 1 s · ignores Retry-After (read from agents/forecast_demand.py)"; the AI suggestion names it the highest unproven risk |
| B2.5 | Click **Absences** in the tool column → open **Classified by** (`docs/screens/02-tool-sources.png`) | "MCP tool manifest · tool annotations in the server's code · Authoritative" (after B4 also "OTel traces") |
| B2.6 | **How this graph was found** (top) | The sources and how many nodes and edges each classified |

### B3 · Journey (`docs/screens/03-journeys.png`)

| # | Do | You should see |
|---|---|---|
| B3.1 | **Journeys** | One suggestion: supervisor → forecast_demand → optimize_roster → compliance → writeback · "Started by POST /roster/run" |
| B3.2 | **Accept**; rename it `Nightly roster generation`; success wording `14 of 14 sites published by 05:00`; **Save** | Saved and accepted |
| B3.3 | **Open** it; look at stage 1's `workday.absences` row | *Faults that apply* lists Rate limit · HTTP 429 among them (the first demo's fault, injected from M5) |

### B4 · Classified from traces: a sandbox run (`docs/screens/04-runtime-plan.png`)

| # | Do | You should see |
|---|---|---|
| B4.1 | **Runtime plan** → **Generate plan** | "Built from docker-compose.yml: 18 service(s)", each on NaviStorm's traced Python template; Azure OpenAI answered by an LLM stub |
| B4.2 | Section *Traffic scenarios*: switch on `POST /roster/run` and `POST /copilot/ask` → **Save draft** → **Approve plan** | Approved |
| B4.3 | **Run in sandbox** (about 3 minutes; the first build is the slowest) | Succeeded: all scenarios passed, 18 of 18 services ready, model calls to gpt-4o-mini answered by a stub, nothing missing from the graph (counts from the 20 Nov run were 9 scenarios, 15 services, about 2,500 spans; not yet re-run with this version) |
| B4.4 | Back to **Topology**; click any agent, tool or system → **Classified by** | **OTel traces** first ("sandbox run on …: code ran … / traffic"), then MCP tool manifest, Compose, Code |

That is the brief's item 3: every node classified from traces and MCP manifests, and every node and edge saying which
source classified it.

## If something does not match

| Symptom | Cause | What to do |
|---|---|---|
| Check lists `agents/forecast_demand.py` as "could not read" | NaviStorm without fix `a3d8542` | Run NaviStorm from branch `wpo-demo` |
| The runtime plan has 0 services, "uses the image wpo-reference:local … left out" | NaviStorm without fix `3cb5a00` | Same |
| Counts differ | The repo or NaviStorm changed | `scripts/check_topology.py` names the exact difference |
| `make up` times out | Docker not running, or port 8080 taken | `docker info`; `AGENTS_PORT=8081 make up` |
| The copilot answers 423 | `COPILOT_HOURS` set to real hours outside them | Unset it (Compose default is always open) |
