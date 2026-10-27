#!/bin/bash
# Local proof of deploy.sh: a bad image rolls back, a missing tag does not
# stop the healthy container, and a model pin does not change the image.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
STATE="$WORK/state"
mkdir -p "$STATE"
PORT=8012
NAME="priceoptima-deploytest"
REPO="priceoptima-deploytest"
trap 'docker rm -f "$NAME" >/dev/null 2>&1 || true; docker images "$REPO" -q | xargs -r docker rmi >/dev/null 2>&1 || true; rm -rf "$WORK"' EXIT

cat >"$WORK/server.py" <<'PY'
from http.server import BaseHTTPRequestHandler, HTTPServer
import os

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ready":
            code = int(os.environ.get("READY_CODE", "200"))
            body = b'{"status":"ready"}' if code == 200 else b'{"status":"not_ready"}'
        else:
            code = 404
            body = b"missing"
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _fmt, *_args):
        return

HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
PY

cat >"$WORK/Dockerfile" <<'EOF'
FROM python:3.11-slim
ARG READY_CODE=200
ENV READY_CODE=$READY_CODE
COPY server.py /server.py
EXPOSE 8000
CMD ["python", "/server.py"]
EOF

build() {
    local tag="$1"
    local code="$2"
    docker build -q -t "$REPO:$tag" --build-arg "READY_CODE=$code" "$WORK" >/dev/null
    sleep 1
}

common=(
    STATE_DIR="$STATE"
    CONTAINER_NAME="$NAME"
    HOST_PORT="$PORT"
    READY_TIMEOUT=8
    ENV_FILE="$STATE/none.env"
    KEEP_IMAGES=3
)

echo "build fixture images"
build good 200
build bad 503
build old 200

echo "first deploy"
env "${common[@]}" PULL=0 bash "$ROOT/scripts/deploy.sh" "$REPO:good"
curl -fsS "http://127.0.0.1:$PORT/ready" >/dev/null
grep -q "^image=$REPO:good$" "$STATE/current.env"
grep -q "^status=ok$" "$STATE/deploy_result"

echo "broken deploy rolls back"
if env "${common[@]}" PULL=0 bash "$ROOT/scripts/deploy.sh" "$REPO:bad"; then
    echo "bad deploy should have failed" >&2
    exit 1
fi
running="$(docker inspect -f '{{.Config.Image}}' "$NAME")"
test "$running" = "$REPO:good"
curl -fsS "http://127.0.0.1:$PORT/ready" >/dev/null
grep -q "^status=rolled_back$" "$STATE/deploy_result"

echo "missing tag does not remove the healthy container"
if env "${common[@]}" PULL=1 bash "$ROOT/scripts/deploy.sh" "$REPO:does-not-exist"; then
    echo "missing tag should have failed" >&2
    exit 1
fi
running="$(docker inspect -f '{{.Config.Image}}' "$NAME")"
test "$running" = "$REPO:good"
curl -fsS "http://127.0.0.1:$PORT/ready" >/dev/null

echo "model pin keeps the same image"
before_id="$(docker inspect -f '{{.Image}}' "$NAME")"
env "${common[@]}" PULL=0 bash "$ROOT/scripts/roll_model.sh" "model-v1"
after_id="$(docker inspect -f '{{.Image}}' "$NAME")"
test "$before_id" = "$after_id"
docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$NAME" | grep -qx "MODEL_VERSION=model-v1"
grep -q "^model_version=model-v1$" "$STATE/current.env"

echo "failed model pin rolls back to the previous pin"
if env "${common[@]}" PULL=0 MODEL_VERSION=model-missing bash "$ROOT/scripts/deploy.sh" "$REPO:bad"; then
    echo "bad model pin should have failed" >&2
    exit 1
fi
docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$NAME" | grep -qx "MODEL_VERSION=model-v1"
curl -fsS "http://127.0.0.1:$PORT/ready" >/dev/null

echo "prune keeps three image ids and the phase2 image"
build extra 200
env "${common[@]}" PULL=0 bash "$ROOT/scripts/deploy.sh" "$REPO:extra"
count="$(docker images --no-trunc "$REPO" --format '{{.ID}}' | sort -u | wc -l)"
count="$(echo "$count" | tr -d ' ')"
if [[ "$count" -gt 3 ]]; then
    echo "expected at most 3 image ids, found $count" >&2
    docker images "$REPO"
    exit 1
fi
docker image inspect priceoptima:phase2 >/dev/null
echo "deploy tests passed"
