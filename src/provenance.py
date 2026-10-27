"""Run identity: git commit and the DVC hash of the raw dataset."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from src.config import project_root


def configure_logging() -> None:
    """Send stage logs to stderr. Pipeline code uses this instead of print."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )


def git_commit(root: Path | None = None) -> str:
    """Return HEAD, or 'unknown' when git is not available."""
    repo = root or project_root()
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"
    return output.strip() or "unknown"


def git_dirty(root: Path | None = None) -> bool:
    """True when tracked files differ from HEAD.

    Untracked files are ignored so a not-yet-committed dvc.lock does not
    look like a code change. The flag tells a reviewer whether the recorded
    commit actually matches the code that trained the model.
    """
    repo = root or project_root()
    try:
        output = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=repo,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return True
    return bool(output.strip())


def dvc_data_hash(dvc_file: Path) -> str:
    """Read the md5 DVC stored for the raw CSV.

    That hash is the dataset version. It stays stable when the path does not,
    which is what a model card should cite.
    """
    if not dvc_file.is_file():
        return "unknown"
    payload = yaml.safe_load(dvc_file.read_text(encoding="utf-8"))
    outs = payload.get("outs") if isinstance(payload, dict) else None
    if not outs:
        return "unknown"
    md5 = outs[0].get("md5")
    return str(md5) if md5 else "unknown"


def dump_json(path: Path, payload: Any) -> None:
    """Write JSON with a trailing newline so diffs stay reviewable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
