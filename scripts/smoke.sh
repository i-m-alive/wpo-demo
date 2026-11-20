#!/usr/bin/env bash
# Builds and starts all 15 services, calls both routes, checks the answers, then stops and removes everything.
# Runs as its own Compose project on port 18080 (AGENTS_PORT), so it never clashes with a demo already running.
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT=wporef-smoke
PORT=${AGENTS_PORT:-18080}
export AGENTS_PORT=$PORT
cleanup() { docker compose -p "$PROJECT" down --remove-orphans --volumes >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "building and starting 15 services..."
docker compose -p "$PROJECT" up --build --detach --wait --wait-timeout 180 >/dev/null
echo "all services healthy: $(docker compose -p "$PROJECT" ps --status running --quiet | wc -l | tr -d ' ') running"

roster=$(curl -fsS -X POST "localhost:$PORT/roster/run" -H 'content-type: application/json' -d '{}')
echo "roster/run  -> $roster" | cut -c1-200
python3 - "$roster" <<'PY'
import json, sys
r = json.loads(sys.argv[1])
assert r["sites"] == 14 and r["published"] is True and r["compliant"] is True and r["rounds"] == 1, r
assert r["forecast"].startswith("Demand site-01:"), r["forecast"]
PY

answer=$(curl -fsS -X POST "localhost:$PORT/copilot/ask" -H 'content-type: application/json' -d '{"question":"Who is on shift at site-04?"}')
echo "copilot/ask -> $answer" | cut -c1-200
python3 - "$answer" <<'PY'
import json, sys
a = json.loads(sys.argv[1])
assert a["site"] == "site-04" and a["answer"].startswith("On site-04 the roster is:"), a
PY

published=$(docker compose -p "$PROJECT" ps --format '{{.Service}} {{.Ports}}' | grep -- '->' | awk '{print $1}' | sort -u | tr '\n' ' ')
[ "$published" = "agents " ] || { echo "only the agents may be published, found: $published"; exit 1; }
echo "published ports: agents only"

echo "smoke test passed"
