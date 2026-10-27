#!/bin/bash
# Idempotent host setup for a small EC2 instance.
# Installs Docker, a 1 GB swap file, and /opt/priceoptima.
# Safe to run again: it does not overwrite an existing .env.prod.
#
# Usage (on the instance, as a user who can sudo):
#   bash scripts/ec2_bootstrap.sh
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/shreyanshhhhhhhh/MLOps_FinaL.git}"
APP_DIR="${APP_DIR:-/opt/priceoptima}"
SRC_DIR="$APP_DIR/src"
SWAP_FILE="${SWAP_FILE:-/swapfile}"

if [[ "$(id -u)" -eq 0 ]]; then
    SUDO=""
    OWNER="${BOOTSTRAP_USER:-ec2-user}"
else
    SUDO="sudo"
    OWNER="${SUDO_USER:-$USER}"
fi

if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
fi
DISTRO="${ID:-unknown}"

as_root() {
    if [[ -n "$SUDO" ]]; then
        sudo "$@"
    else
        "$@"
    fi
}

ensure_swap() {
    if swapon --show | grep -q "$SWAP_FILE"; then
        echo "swap already active at $SWAP_FILE"
        return 0
    fi
    if [[ ! -f "$SWAP_FILE" ]]; then
        if ! as_root fallocate -l 1G "$SWAP_FILE"; then
            as_root dd if=/dev/zero of="$SWAP_FILE" bs=1M count=1024
        fi
        as_root chmod 600 "$SWAP_FILE"
        as_root mkswap "$SWAP_FILE"
    fi
    as_root swapon "$SWAP_FILE"
    if ! grep -qE "^${SWAP_FILE}[[:space:]]" /etc/fstab; then
        echo "$SWAP_FILE none swap sw 0 0" | as_root tee -a /etc/fstab >/dev/null
    fi
    echo "swap enabled"
}

install_packages() {
    case "$DISTRO" in
        amzn)
            as_root dnf install -y docker git curl ca-certificates
            ;;
        ubuntu | debian)
            as_root apt-get update
            as_root apt-get install -y docker.io git curl ca-certificates
            ;;
        *)
            echo "unsupported distro: $DISTRO (use Ubuntu 22.04 or Amazon Linux 2023)" >&2
            exit 1
            ;;
    esac
}

ensure_swap

if ! command -v docker >/dev/null 2>&1 || ! command -v git >/dev/null 2>&1; then
    install_packages
fi
as_root systemctl enable --now docker
as_root usermod -aG docker "$OWNER"

as_root mkdir -p "$APP_DIR"
if [[ ! -d "$SRC_DIR/.git" ]]; then
    as_root git clone "$REPO_URL" "$SRC_DIR"
fi
as_root chown -R "$OWNER:$OWNER" "$APP_DIR"

if [[ ! -f "$APP_DIR/.env.prod" ]]; then
    if [[ ! -f "$SRC_DIR/.env.prod.example" ]]; then
        echo "missing $SRC_DIR/.env.prod.example; pull main before the first bootstrap" >&2
        exit 1
    fi
    cp "$SRC_DIR/.env.prod.example" "$APP_DIR/.env.prod"
    chmod 600 "$APP_DIR/.env.prod"
    echo "wrote $APP_DIR/.env.prod from the example (mode 600)"
else
    echo "keeping existing $APP_DIR/.env.prod"
fi

echo "bootstrap complete for $OWNER"
echo "open a new SSH session so the docker group applies, then run scripts/deploy.sh"
