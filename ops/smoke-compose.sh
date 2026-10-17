#!/usr/bin/env bash
# End-to-end smoke test of the container stack (docker-compose.yml): builds the images, starts PostGIS + migrations + API
# + web, and exercises the real application through the nginx proxy. Used by CI (job `containers`) and runnable locally:
#
#   bash ops/smoke-compose.sh          # needs Docker with the compose plugin, curl and jq
#
# It creates a throwaway .env.compose with random secrets if you have none (and removes it afterwards), and always
# tears the stack down, including volumes. It never reads backend/.env, so it cannot touch a hosted database.
set -euo pipefail
cd "$(dirname "$0")/.."

ENVF=.env.compose
GENERATED=0
if [ ! -f "$ENVF" ]; then
  GENERATED=1
  {
    echo "POSTGRES_PASSWORD=$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)"
    echo "JWT_SECRET=$(head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 48)"
  } > "$ENVF"
fi
dc() { docker compose --env-file "$ENVF" "$@"; }
cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then echo "---- container logs (failure) ----"; dc logs --no-color --tail=60 || true; fi
  dc down -v --remove-orphans >/dev/null 2>&1 || true
  [ "$GENERATED" = "1" ] && rm -f "$ENVF"
  exit "$status"
}
trap cleanup EXIT

pass() { echo "  PASS  $1"; }
fail() { echo "  FAIL  $1" >&2; exit 1; }
WEB="http://127.0.0.1:${WEB_PORT:-8080}"
API="http://127.0.0.1:${BACKEND_PORT:-8000}"
J='content-type: application/json'

echo "== build and start"
export WORKER_POLL_INTERVAL_S=3   # the worker looks for due agent runs every 3 s here (60 s by default)
dc up -d --build
for i in $(seq 1 90); do
  if curl -fsS "$API/healthz" >/dev/null 2>&1 && curl -fsS "$WEB/healthz" >/dev/null 2>&1; then break; fi
  sleep 2
  [ "$i" = "90" ] && fail "stack did not become healthy in 180 s"
done
pass "API and web answer their health checks"

echo "== migrations and database"
code=$(docker inspect "$(dc ps -aq migrate)" --format '{{.State.ExitCode}}')
[ "$code" = "0" ] && pass "migration job exited 0" || fail "migration job exit code $code"
[ "$(curl -fsS -o /dev/null -w '%{http_code}' "$API/readyz")" = "200" ] && pass "readiness (database reachable) is 200" || fail "readyz"
ver=$(dc exec -T db psql -U postgres -d greenguardian -Atc "select extensions.postgis_version()")
[ -n "$ver" ] && pass "PostGIS installed in the 'extensions' schema ($ver)" || fail "PostGIS missing"
rev=$(dc exec -T db psql -U postgres -d greenguardian -Atc "select version_num from greenguardian.alembic_version")
[ -n "$rev" ] && pass "application schema at migration $rev" || fail "no alembic revision"

echo "== web: static app, headers, proxy"
curl -fsS "$WEB/" | grep -q '<div id="root"' && pass "SPA served" || fail "SPA not served"
curl -fsS "$WEB/w/anything/deep/link" | grep -q '<div id="root"' && pass "deep links fall back to the SPA" || fail "SPA fallback"
hdrs=$(curl -sI "$WEB/")
for h in "content-security-policy" "x-content-type-options: nosniff" "x-frame-options: deny"; do
  echo "$hdrs" | tr 'A-Z' 'a-z' | grep -q "$h" && pass "header $h" || fail "missing header $h"
done
resp=$(curl -si "$WEB/api/v1/me")
echo "$resp" | head -1 | grep -q " 401" && pass "/api is proxied to the API (401 without a token)" || fail "proxy"
echo "$resp" | tr -d '\r' | grep -i '^x-request-id: [0-9a-f]\{32\}$' >/dev/null && pass "nginx request ID reaches the API and comes back" || fail "request id"

echo "== the application works end to end through the proxy"
EMAIL="smoke-$RANDOM@example.com"; PW="Smoke-$(head -c 12 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 16)"
curl -fsS -X POST "$WEB/api/v1/auth/register" -H "$J" -d "{\"email\":\"$EMAIL\",\"password\":\"$PW\",\"name\":\"Smoke\"}" >/dev/null && pass "register"
TOKEN=$(curl -fsS -X POST "$WEB/api/v1/auth/login" -H "$J" -d "{\"email\":\"$EMAIL\",\"password\":\"$PW\"}" | jq -r .access_token)
[ -n "$TOKEN" ] && [ "$TOKEN" != "null" ] && pass "login" || fail "login"
A="authorization: Bearer $TOKEN"
WS=$(curl -fsS -X POST "$WEB/api/v1/workspaces" -H "$J" -H "$A" -d '{"name":"Smoke farm","mode":"agricultural_production"}' | jq -r .id)
[ -n "$WS" ] && [ "$WS" != "null" ] && pass "create workspace" || fail "workspace"
ASSET=$(curl -fsS -X POST "$WEB/api/v1/workspaces/$WS/assets" -H "$J" -H "$A" -d '{"label":"Batch 1","kind":"crop_batch","latitude":19.07,"longitude":72.87}' | jq -r .id)
[ -n "$ASSET" ] && [ "$ASSET" != "null" ] && pass "create a located asset" || fail "asset"
curl -fsS "$WEB/api/v1/workspaces/$WS/map/layers/assets" -H "$A" | jq -e '.features | length == 1' >/dev/null && pass "the PostGIS-backed map query returns it" || fail "map"

# a valid 1x1 PNG; proves the non-root API process can write to the storage volume and the bytes round-trip intact
echo "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAHnOcmwAAAABJRU5ErkJggg==" | base64 -d > /tmp/smoke.png
EV=$(curl -fsS -X POST "$WEB/api/v1/workspaces/$WS/evidence" -H "$A" -F "asset_id=$ASSET" -F "file=@/tmp/smoke.png;type=image/png" | jq -r .id)
[ -n "$EV" ] && [ "$EV" != "null" ] && pass "upload a photo" || fail "upload"
curl -fsS "$WEB/api/v1/workspaces/$WS/evidence/$EV/content" -H "$A" -o /tmp/smoke-back.png
cmp /tmp/smoke.png /tmp/smoke-back.png && pass "the photo comes back byte for byte" || fail "photo bytes differ"
dc exec -T backend sh -c 'test -n "$(find /data/storage -type f | head -1)"' && pass "the file is on the storage volume" || fail "no stored file"

echo "== the background worker runs the agent on a schedule"
for i in $(seq 1 60); do
  [ "$(docker inspect "$(dc ps -q worker)" --format '{{.State.Health.Status}}')" = "healthy" ] && break
  sleep 2
  [ "$i" = "60" ] && fail "worker did not become healthy in 120 s"
done
pass "worker container is healthy (its heartbeat is fresh)"
for i in $(seq 1 30); do
  RUNS=$(curl -fsS "$WEB/api/v1/workspaces/$WS/agent/runs" -H "$A")
  echo "$RUNS" | jq -e '[.items[] | select(.trigger == "scheduled" and .status == "succeeded")] | length >= 1' >/dev/null && break
  sleep 2
  [ "$i" = "30" ] && fail "no scheduled agent run appeared for the new workspace within 60 s"
done
pass "a scheduled agent run was executed and recorded for the new workspace"
echo "$RUNS" | jq -e '.items[0].worker_id | length > 0' >/dev/null && pass "the run names the worker that executed it" || fail "run content"
[ "$(dc exec -T worker id -u)" = "10001" ] && pass "worker runs as uid 10001" || fail "worker runs as root"
dc stop -t 30 worker >/dev/null
code=$(docker inspect "$(dc ps -aq worker)" --format '{{.State.ExitCode}}')
[ "$code" = "0" ] && pass "worker shuts down cleanly on SIGTERM (exit 0)" || fail "worker exit code $code on SIGTERM"

echo "== containers run as non-root and hold no secrets"
[ "$(dc exec -T backend id -u)" = "10001" ] && pass "API runs as uid 10001" || fail "API runs as root"
[ "$(dc exec -T web id -u)" = "101" ] && pass "web runs as uid 101" || fail "web runs as root"
if docker history --no-trunc greenguardian-backend:local greenguardian-web:local 2>/dev/null | grep -i -E 'JWT_SECRET|POSTGRES_PASSWORD|DATABASE_URL=.*@'; then fail "a secret appears in an image layer"; fi
pass "no secret in any image layer"
if docker run --rm --entrypoint python greenguardian-backend:local -c "from app.core.config import Settings; Settings(database_url='postgresql://u@h/d', _env_file=None)" >/dev/null 2>&1; then
  fail "the API image started without a JWT_SECRET"
fi
pass "the API refuses to start without a signing secret"

echo "SMOKE TEST PASSED"
