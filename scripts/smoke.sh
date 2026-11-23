#!/usr/bin/env bash
# Builds and starts all 18 services, calls both routes, checks the answers, then two stand-in failure modes over the real
# MCP path (an infeasible solver; a throttled Workday, which W1 retries forever), then stops and removes everything.
# Runs as its own Compose project on port 18080 (AGENTS_PORT), so it never clashes with a demo already running.
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT=wporef-smoke
PORT=${AGENTS_PORT:-18080}
export AGENTS_PORT=$PORT
compose() { docker compose -p "$PROJECT" "$@"; }
cleanup() { compose down --remove-orphans --volumes >/dev/null 2>&1 || true; }
trap cleanup EXIT
run() { curl -fsS --max-time "$2" -X POST "localhost:$PORT/roster/run" -H 'content-type: application/json' -d "$1"; }

echo "building and starting 18 services..."
compose up --build --detach --wait --wait-timeout 180 >/dev/null
running=$(compose ps --status running --quiet | wc -l | tr -d ' ')
echo "all services healthy: $running running"
[ "$running" = 18 ] || { echo "expected 18 services, found $running"; exit 1; }

roster=$(run '{}' 60)
echo "roster/run  -> $roster" | cut -c1-200
python3 - "$roster" <<'PY'
import json, sys
r = json.loads(sys.argv[1])
assert r["sites"] == 14 and r["published"] is True and r["compliant"] is True and r["rounds"] == 1, r
assert r["forecast"].startswith("Demand S01: 5 people on S01-L1, early shift, 1 absent;"), r["forecast"]
assert r["forecast_ok"] is True and r["solver_status"] == "OK", r  # the model answered through the LLM stand-in
PY

answer=$(curl -fsS -X POST "localhost:$PORT/copilot/ask" -H 'content-type: application/json' -d '{"question":"Who is on shift at S04?"}')
echo "copilot/ask -> $answer" | cut -c1-200
python3 - "$answer" <<'PY'
import json, sys
a = json.loads(sys.argv[1])
assert a == {"site": "S04", "answer": "On S04 the roster is: early shift on S04-L1: W01, W02, W03, W04, W05.",
             "answer_ok": True}, a
PY

published=$(compose ps --format '{{.Service}} {{.Ports}}' | grep -- '->' | awk '{print $1}' | sort -u | tr '\n' ' ')
[ "$published" = "agents " ] || { echo "only the agents may be published, found: $published"; exit 1; }
echo "published ports: agents only"

echo "failure mode: cuOpt infeasible..."
CUOPT_MODE=infeasible compose up --detach --wait --no-deps stub-cuopt >/dev/null 2>&1
infeasible=$(run '{}' 60)
echo "roster/run  -> $infeasible" | cut -c1-200
python3 - "$infeasible" <<'PY'
import json, sys
r = json.loads(sys.argv[1])
assert r["published"] is False and r["compliant"] is False and r["rounds"] == 3, r
assert r["breaches"] == ["the solver returned no roster"], r
assert r["solver_status"] == "no answer after max_iter (INFEASIBLE)", r
PY
CUOPT_MODE=normal compose up --detach --wait --no-deps stub-cuopt >/dev/null 2>&1

echo "failure mode: Workday throttled (W1 retries forever, so the call below is cut off after 8 s)..."
WORKDAY_MODE=throttle WORKDAY_RETRY_AFTER=120 compose up --detach --wait --no-deps stub-workday >/dev/null 2>&1
run '{}' 8 >/dev/null 2>&1 && { echo "roster/run answered while Workday was throttled: W1 should retry forever"; exit 1; }
throttled=$(compose logs stub-workday 2>/dev/null | grep -c '" 429' || true)
echo "Workday answered 429 (Retry-After: 120) $throttled times in 8 s"
[ "$throttled" -ge 5 ] || { echo "expected the forecast to retry about once a second, found $throttled 429s"; exit 1; }

echo "smoke test passed"
