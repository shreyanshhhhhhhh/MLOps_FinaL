#!/bin/sh
# Pull models/model.pkl, the preprocessor, and the model card from the DVC remote.
# Credentials are whatever the environment or the instance role already has.
# A failure here retries. It does not exit the container.
set -u

cd /app || exit 1

log() {
    printf '%s\n' "$*"
}

checkout_version() {
    version="$1"
    repo="${GIT_REPO_URL:-}"
    if [ -z "$repo" ]; then
        log "MODEL_VERSION is set but GIT_REPO_URL is empty"
        return 1
    fi
    dest="$(mktemp -d)"
    if git clone --depth 1 --branch "$version" "$repo" "$dest"; then
        :
    else
        rm -rf "$dest"
        dest="$(mktemp -d)"
        git clone "$repo" "$dest" || return 1
        git -C "$dest" checkout "$version" || {
            rm -rf "$dest"
            return 1
        }
    fi
    if [ ! -f "$dest/dvc.lock" ]; then
        log "revision $version has no dvc.lock"
        rm -rf "$dest"
        return 1
    fi
    cp "$dest/dvc.lock" /app/dvc.lock
    rm -rf "$dest"
    log "using dvc.lock from $version"
}

pull_once() {
    if [ -n "${MODEL_VERSION:-}" ]; then
        checkout_version "$MODEL_VERSION" || return 1
    fi
    if [ -n "${DVC_REMOTE:-}" ]; then
        dvc remote default "$DVC_REMOTE" || return 1
    fi
    if [ -n "${DVC_STORAGE_URL:-}" ]; then
        dvc remote modify local url "$DVC_STORAGE_URL" || return 1
    fi
    dvc config core.no_scm true || return 1
    dvc pull models/model.pkl models/model_meta.json models/preprocessor.joblib || return 1
    for file in models/model.pkl models/model_meta.json models/preprocessor.joblib; do
        if [ ! -s "$file" ]; then
            log "missing or empty $file after dvc pull"
            return 1
        fi
    done
    printf '%s\n' "${MODEL_VERSION:-workspace}" > models/VERSION
    log "model files are present"
}

delay=2
attempt=0
while true; do
    attempt=$((attempt + 1))
    if pull_once; then
        log "model fetch succeeded on attempt ${attempt}"
        exit 0
    fi
    log "model fetch attempt ${attempt} failed; retrying in ${delay}s"
    sleep "$delay"
    if [ "$delay" -lt 60 ]; then
        delay=$((delay * 2))
        if [ "$delay" -gt 60 ]; then
            delay=60
        fi
    fi
done
