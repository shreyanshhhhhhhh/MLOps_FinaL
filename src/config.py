"""Load params.yaml, the single source of truth for the pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REQUIRED_KEYS = ("seed", "split", "preprocess", "features", "models", "paths", "tracking")


def project_root() -> Path:
    """Return the repository root (parent of src/)."""
    return Path(__file__).resolve().parents[1]


def load_params(path: Path | None = None) -> dict[str, Any]:
    """Read params.yaml and refuse to run if a required section is missing.

    The chronological split is required so a random shuffle cannot leak
    future months into training. Other strategies are rejected on purpose.
    """
    params_path = path or project_root() / "params.yaml"
    with params_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{params_path} must contain a YAML mapping")
    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        raise ValueError(f"{params_path} missing keys: {missing}")
    strategy = data["split"].get("strategy")
    if strategy != "chronological":
        raise ValueError("split.strategy must be 'chronological' so the test set is future months")
    test_size = float(data["split"]["test_size"])
    if not 0 < test_size < 1:
        raise ValueError("split.test_size must be between 0 and 1")
    return data


def resolve_path(root: Path, value: str) -> Path:
    """Resolve a params path against the repo root unless it is already absolute."""
    path = Path(value)
    return path if path.is_absolute() else root / path
