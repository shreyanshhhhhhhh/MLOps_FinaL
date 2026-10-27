#!/bin/bash
# Pull one image, replace the running container, and roll back if /ready fails.
#
# Usage: deploy.sh <image>
#   IMAGE is a registry tag such as dockerhubuser/priceoptima:abc1234
#
# Environment:
#   ENV_FILE        Container env file. Default /opt/priceoptima/.env.prod
#   CONTAINER_NAME  Default priceoptima
#   HOST_PORT       Host port mapped to container port 8000. Read from
#                   ENV_FILE when unset. Default 8000.
#   READY_TIMEOUT   Seconds to wait for /ready. Default 120.
#   STATE_DIR       Where current.env, previous.env, and deploy_result live.
#   MODEL_VERSION   When set (including empty), overrides the env file for
#                   this start. scripts/roll_model.sh sets it. A code deploy
#                   leaves it unset so the env file keeps the current model.
#   PULL            1 (default) runs docker pull first. Tests of local
#                   images set PULL=0. A failed pull does not stop the
#                   container that is already serving.
#   KEEP_IMAGES     How many image IDs of this repository to retain. Default 3.
set -euo pipefail

IMAGE="${1:-}"
if [[ -z "$IMAGE" ]]; then
    echo "usage: deploy.sh <image>" >&2
    exit 2
fi

STATE_DIR="${STATE_DIR:-/opt/priceoptima}"
ENV_FILE="${ENV_FILE:-$STATE_DIR/.env.prod}"
CONTAINER_NAME="${CONTAINER_NAME:-priceoptima}"
READY_TIMEOUT="${READY_TIMEOUT:-120}"
KEEP_IMAGES="${KEEP_IMAGES:-3}"
mkdir -p "$STATE_DIR"

if [[ -z "${HOST_PORT:-}" && -f "$ENV_FILE" ]]; then
    HOST_PORT="$(sed -n 's/^HOST_PORT=//p' "$ENV_FILE" | head -1 | tr -d '[:space:]')"
fi
HOST_PORT="${HOST_PORT:-8000}"

write_state() {
    local file="$1"
    local image="$2"
    local model_version="$3"
    local tmp
    tmp="$(mktemp "$STATE_DIR/.state.XXXXXX")"
    printf 'image=%s\nmodel_version=%s\n' "$image" "$model_version" >"$tmp"
    chmod 600 "$tmp"
    mv "$tmp" "$file"
}

write_result() {
    local status="$1"
    local image="$2"
    local model_version="$3"
    local tmp
    tmp="$(mktemp "$STATE_DIR/.result.XXXXXX")"
    printf 'status=%s\nimage=%s\nmodel_version=%s\n' "$status" "$image" "$model_version" >"$tmp"
    chmod 600 "$tmp"
    mv "$tmp" "$STATE_DIR/deploy_result"
}

container_model_version() {
    docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$CONTAINER_NAME" 2>/dev/null \
        | sed -n 's/^MODEL_VERSION=//p' \
        | head -1 \
        || true
}

remember_previous() {
    PREV_IMAGE=""
    PREV_MODEL=""
    if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
        PREV_IMAGE="$(docker inspect -f '{{.Config.Image}}' "$CONTAINER_NAME")"
        PREV_MODEL="$(container_model_version)"
        write_state "$STATE_DIR/previous.env" "$PREV_IMAGE" "$PREV_MODEL"
    elif [[ -f "$STATE_DIR/current.env" ]]; then
        PREV_IMAGE="$(sed -n 's/^image=//p' "$STATE_DIR/current.env" | head -1)"
        PREV_MODEL="$(sed -n 's/^model_version=//p' "$STATE_DIR/current.env" | head -1)"
        write_state "$STATE_DIR/previous.env" "$PREV_IMAGE" "$PREV_MODEL"
    fi
}

start_container() {
    local image="$1"
    local override_model="$2"
    local model_version="$3"
    local -a cmd

    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
    cmd=(docker run -d
        --name "$CONTAINER_NAME"
        --restart unless-stopped
        -p "${HOST_PORT}:8000")
    if [[ -f "$ENV_FILE" ]]; then
        cmd+=(--env-file "$ENV_FILE")
    fi
    if [[ "$override_model" == "1" ]]; then
        cmd+=(-e "MODEL_VERSION=${model_version}")
    fi
    cmd+=("$image")
    "${cmd[@]}" >/dev/null
}

wait_ready() {
    local deadline=$((SECONDS + READY_TIMEOUT))
    while [[ "$SECONDS" -lt "$deadline" ]]; do
        if curl -fsS "http://127.0.0.1:${HOST_PORT}/ready" >/dev/null 2>&1; then
            return 0
        fi
        if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
            local running
            running="$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME")"
            if [[ "$running" != "true" ]]; then
                echo "container exited before /ready" >&2
                docker logs --tail 40 "$CONTAINER_NAME" >&2 || true
                return 1
            fi
        fi
        sleep 2
    done
    echo "/ready did not return 200 within ${READY_TIMEOUT}s" >&2
    docker logs --tail 40 "$CONTAINER_NAME" >&2 || true
    return 1
}

rollback() {
    echo "deploy of ${IMAGE} failed" >&2
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
    if [[ -z "${PREV_IMAGE}" ]]; then
        write_result "failed" "$IMAGE" "${NEW_MODEL}"
        echo "no previous image to roll back to" >&2
        exit 1
    fi
    echo "rolling back to ${PREV_IMAGE}" >&2
    # A model-release failure restores the previous pin. A code deploy
    # that had preserved the live pin restores that same pin.
    if [[ "$OVERRIDE_MODEL" == "1" ]]; then
        start_container "$PREV_IMAGE" 1 "$PREV_MODEL"
    else
        start_container "$PREV_IMAGE" 0 ""
    fi
    if wait_ready; then
        write_state "$STATE_DIR/current.env" "$PREV_IMAGE" "$PREV_MODEL"
        write_result "rolled_back" "$PREV_IMAGE" "$PREV_MODEL"
        echo "rolled back to ${PREV_IMAGE}" >&2
    else
        write_result "rollback_failed" "$PREV_IMAGE" "$PREV_MODEL"
        echo "rollback to ${PREV_IMAGE} did not become ready" >&2
    fi
    exit 1
}

prune_images() {
    local repo="$1"
    local -a newest=()
    local id created
    # created is only the sort key in the stream below.
    local in_use=""

    if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
        in_use="$(docker inspect -f '{{.Image}}' "$CONTAINER_NAME")"
    fi

    while IFS=$'\t' read -r created id; do
        [[ -n "$created" && -n "$id" ]] || continue
        local seen=0
        local kept
        for kept in "${newest[@]+"${newest[@]}"}"; do
            if [[ "$kept" == "$id" ]]; then
                seen=1
                break
            fi
        done
        if [[ "$seen" == "0" ]]; then
            newest+=("$id")
        fi
    done < <(docker images --no-trunc "$repo" --format '{{.CreatedAt}}\t{{.ID}}' | sort -r)

    local keep_count=0
    local candidate
    for candidate in "${newest[@]+"${newest[@]}"}"; do
        keep_count=$((keep_count + 1))
        if [[ "$keep_count" -le "$KEEP_IMAGES" || "$candidate" == "$in_use" ]]; then
            continue
        fi
        docker rmi "$candidate" >/dev/null 2>&1 || true
    done
}

if ! docker info >/dev/null 2>&1; then
    echo "docker is not available to this user" >&2
    exit 1
fi

if [[ "${PULL:-1}" == "1" ]]; then
    docker pull "$IMAGE"
fi

remember_previous

# MODEL_VERSION in this process is an explicit pin (model release).
# A code deploy leaves it unset and keeps the pin already on the container,
# so shipping code does not silently change the model. The first deploy
# has no container yet and lets .env.prod supply the pin.
OVERRIDE_MODEL=0
NEW_MODEL=""
if [[ -n "${MODEL_VERSION+x}" ]]; then
    OVERRIDE_MODEL=1
    NEW_MODEL="$MODEL_VERSION"
elif [[ -n "$PREV_IMAGE" ]]; then
    OVERRIDE_MODEL=1
    NEW_MODEL="$PREV_MODEL"
fi

if ! start_container "$IMAGE" "$OVERRIDE_MODEL" "$NEW_MODEL"; then
    rollback
fi
if ! wait_ready; then
    rollback
fi

if [[ "$OVERRIDE_MODEL" == "1" ]]; then
    RUNNING_MODEL="$NEW_MODEL"
else
    RUNNING_MODEL="$(container_model_version)"
fi
write_state "$STATE_DIR/current.env" "$IMAGE" "$RUNNING_MODEL"
write_result "ok" "$IMAGE" "$RUNNING_MODEL"

REPO="${IMAGE%:*}"
if [[ "$REPO" == "$IMAGE" ]]; then
    REPO="$IMAGE"
fi
prune_images "$REPO"
echo "deployed ${IMAGE}"
