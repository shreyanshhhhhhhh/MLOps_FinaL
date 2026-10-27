#!/bin/bash
# Restart the current image with a different MODEL_VERSION.
# The image is not rebuilt and not replaced. scripts/deploy.sh still
# waits for /ready and rolls back to the previous model version on failure.
#
# Usage: roll_model.sh <model-version>
#   model-version is a git tag or commit, for example model-v1.
set -euo pipefail

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
    echo "usage: roll_model.sh <model-version>" >&2
    exit 2
fi

STATE_DIR="${STATE_DIR:-/opt/priceoptima}"
CONTAINER_NAME="${CONTAINER_NAME:-priceoptima}"
IMAGE=""
if [[ -f "$STATE_DIR/current.env" ]]; then
    IMAGE="$(sed -n 's/^image=//p' "$STATE_DIR/current.env" | head -1)"
fi
if [[ -z "$IMAGE" ]]; then
    IMAGE="$(docker inspect -f '{{.Config.Image}}' "$CONTAINER_NAME")"
fi

export MODEL_VERSION="$VERSION"
exec "$(dirname "$0")/deploy.sh" "$IMAGE"
