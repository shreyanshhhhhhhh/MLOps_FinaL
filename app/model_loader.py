"""Load the promoted model and score demand with the training feature code."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from app.metrics import METRICS
from app.schemas import ModelInfo
from src.config import load_params, project_root
from src.features import add_engineered_features, transform_frame

logger = logging.getLogger(__name__)

MODEL_FILENAME = "model.pkl"
META_FILENAME = "model_meta.json"
PREPROCESSOR_FILENAME = "preprocessor.joblib"
VERSION_FILENAME = "VERSION"


class ModelService:
    """Holds the estimator, the fitted preprocessor, and the model card.

    ``ready`` stays false until all three files have been read. A failed
    fetch leaves the process up so ``/health`` can succeed while ``/ready``
    stays 503.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.model: Any = None
        self.bundle: dict[str, Any] | None = None
        self.meta: dict[str, Any] | None = None
        self.load_time: str | None = None
        self.model_version: str | None = None
        self.error: str | None = "model is not loaded"

    def reset(self) -> None:
        with self._lock:
            self.model = None
            self.bundle = None
            self.meta = None
            self.load_time = None
            self.model_version = None
            self.error = "model is not loaded"

    @property
    def ready(self) -> bool:
        return self.model is not None and self.bundle is not None and self.meta is not None

    def models_dir(self) -> Path:
        override = os.environ.get("MODELS_DIR")
        if override:
            return Path(override)
        return project_root() / "models"

    def files_ready(self, models_dir: Path | None = None) -> bool:
        directory = models_dir or self.models_dir()
        return all(
            (directory / name).is_file() and (directory / name).stat().st_size > 0
            for name in (MODEL_FILENAME, META_FILENAME, PREPROCESSOR_FILENAME)
        )

    def load_from_disk(self, models_dir: Path | None = None) -> None:
        directory = models_dir or self.models_dir()
        model = joblib.load(directory / MODEL_FILENAME)
        bundle = joblib.load(directory / PREPROCESSOR_FILENAME)
        meta = json.loads((directory / META_FILENAME).read_text(encoding="utf-8"))
        if not isinstance(bundle, dict) or "preprocessor" not in bundle:
            raise ValueError("preprocessor.joblib is not the training bundle")
        version_path = directory / VERSION_FILENAME
        version = None
        if version_path.is_file():
            version = version_path.read_text(encoding="utf-8").strip()
        with self._lock:
            self.model = model
            self.bundle = bundle
            self.meta = meta
            self.model_version = version or None
            self.load_time = datetime.now(UTC).isoformat()
            self.error = None
        logger.info(
            "loaded model %s version=%s",
            meta.get("model_name", "unknown"),
            self.model_version or "unset",
        )

    def install_for_tests(
        self,
        model: Any,
        bundle: dict[str, Any],
        meta: dict[str, Any],
        *,
        model_version: str | None = "test",
    ) -> None:
        """Register an in-memory model. Used by the API tests, not by the container."""
        with self._lock:
            self.model = model
            self.bundle = bundle
            self.meta = meta
            self.model_version = model_version
            self.load_time = datetime.now(UTC).isoformat()
            self.error = None

    def info(self) -> ModelInfo:
        if not self.ready or self.meta is None or self.load_time is None:
            raise RuntimeError(self.error or "model is not loaded")
        metrics = self.meta.get("metrics") or {}
        return ModelInfo(
            model_name=str(self.meta.get("model_name", "unknown")),
            metrics={str(key): _as_float(value) for key, value in metrics.items()},
            git_commit=str(self.meta.get("git_commit", "unknown")),
            dvc_data_hash=str(self.meta.get("dvc_data_hash", "unknown")),
            load_time=self.load_time,
            model_version=self.model_version,
        )

    def predict_qty(self, context: dict[str, Any], unit_price: float) -> tuple[float, float]:
        """Return ``(floored demand, raw model output)``.

        Feature construction calls ``add_engineered_features`` and
        ``transform_frame`` from ``src.features``. Those are the functions
        the DVC features stage uses, so the ratio, the logs, and the scaler
        cannot drift from training.
        """
        if not self.ready or self.bundle is None or self.model is None:
            raise RuntimeError(self.error or "model is not loaded")
        row = dict(context)
        row["unit_price"] = unit_price
        frame = pd.DataFrame([row])
        features_cfg = load_params()["features"]
        engineered = add_engineered_features(
            frame,
            list(features_cfg["competitor_price_columns"]),
            price_column=features_cfg["price_column"],
            lag_column=features_cfg["lag_column"],
            target_column=None,
        )
        matrix = transform_frame(self.bundle, engineered)
        raw = float(self.model.predict(matrix)[0])
        METRICS.increment_predictions()
        return max(raw, 0.0), raw

    def watch(self, interval_seconds: float = 2.0) -> None:
        """Poll disk until a fetch drops the three artifacts in place."""
        while not self.ready:
            try:
                if self.files_ready():
                    self.load_from_disk()
                    if self.ready:
                        return
            except Exception as exc:
                self.error = str(exc)
                logger.exception("model load failed; /ready stays 503")
            time.sleep(interval_seconds)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


SERVICE = ModelService()
