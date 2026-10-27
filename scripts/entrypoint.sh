#!/bin/sh
# Start uvicorn even when the model pull fails. fetch_model.sh retries in
# the background; /ready stays 503 until the files are on disk and loaded.
set -u

cd /app
export DVC_NO_ANALYTICS=1
export PYTHONUNBUFFERED=1
export HOME="${HOME:-/home/appuser}"
mkdir -p "$HOME"

# file:// clones and a read-only mount of the repo are not the container user.
git config --global --add safe.directory '*' || true
git config --global --add safe.directory /opt/src || true

/app/scripts/fetch_model.sh &

exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --no-access-log
