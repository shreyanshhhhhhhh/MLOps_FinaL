#!/bin/sh
# Cron probe for the serving container. Exit non-zero when /ready is not 200.
# Usage: scripts/healthcheck.sh
#   READY_URL   default http://127.0.0.1:8000/ready
#   HEALTH_LOG  default /opt/priceoptima/health.log
set -u

URL="${READY_URL:-http://127.0.0.1:${HOST_PORT:-8000}/ready}"
LOG="${HEALTH_LOG:-/opt/priceoptima/health.log}"
mkdir -p "$(dirname "$LOG")"

code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$URL" || echo 000)"
printf '%s ready=%s url=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$code" "$URL" >>"$LOG"
[ "$code" = "200" ]
