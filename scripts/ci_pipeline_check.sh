#!/bin/sh
# Confirm the committed DVC lock matches the workspace.
# CI sets DVC_REMOTE=s3 when AWS secrets exist, and DVC_REMOTE=local otherwise.
# The local remote is the committed dvc-storage directory. A laptop that
# already has the workspace files can set SKIP_DVC_PULL=1.
set -eu

cd "$(dirname "$0")/.."
export DVC_NO_ANALYTICS=1

if [ -n "${DVC_REMOTE:-}" ]; then
    dvc remote default "$DVC_REMOTE"
fi

if [ "${SKIP_DVC_PULL:-}" != "1" ]; then
    dvc pull
fi

status_file="$(mktemp)"
dry_file="$(mktemp)"
trap 'rm -f "$status_file" "$dry_file"' EXIT

dvc status | tee "$status_file"
grep -q "Data and pipelines are up to date." "$status_file"

dvc repro --dry | tee "$dry_file"
grep -q "Data and pipelines are up to date." "$dry_file"
echo "pipeline check passed"
