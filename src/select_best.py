"""Promote the lowest test-RMSE MLflow run into the DVC model registry."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import mlflow
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

from src.config import load_params, project_root, resolve_path
from src.provenance import configure_logging, dump_json

logger = logging.getLogger(__name__)


def _metric(run: Any, name: str) -> float | None:
    value = run.data.metrics.get(name)
    if value is None:
        return None
    return float(value)


def choose_best_run(runs: list[Any]) -> Any:
    """Pick the finished run with the lowest test RMSE.

    Equal scores keep the later run, then the smaller run id. A repeated
    sweep of a deterministic model would otherwise promote the oldest
    identical run and disagree with the evaluate stage.
    """
    ranked = [run for run in runs if _metric(run, "test_rmse") is not None]
    if not ranked:
        raise RuntimeError("no MLflow runs with test_rmse were found")

    def sort_key(run: Any) -> tuple[float, int, str]:
        started = int(run.info.start_time or 0)
        rmse = _metric(run, "test_rmse")
        if rmse is None:
            raise RuntimeError(f"run {run.info.run_id} was ranked without test_rmse")
        return (rmse, -started, run.info.run_id)

    ranked.sort(key=sort_key)
    return ranked[0]


def _feature_list(run_id: str, fallback: list[str]) -> list[str]:
    try:
        path = mlflow.artifacts.download_artifacts(artifact_uri=f"runs:/{run_id}/feature_list.json")
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (MlflowException, OSError, json.JSONDecodeError):
        logger.warning("feature_list.json missing for %s; using preprocessor names", run_id)
        return fallback
    features = payload.get("features")
    if isinstance(features, list) and features:
        return [str(name) for name in features]
    return fallback


def main() -> int:
    """Query MLflow and write models/model.pkl plus models/model_meta.json."""
    configure_logging()
    params = load_params()
    root = project_root()
    models_dir = resolve_path(root, params["paths"]["models_dir"])
    metrics_dir = resolve_path(root, params["paths"]["metrics_dir"])
    tracking_uri = str(resolve_path(root, params["tracking"]["tracking_uri"]))
    experiment_name = params["tracking"]["experiment_name"]
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient(tracking_uri=tracking_uri)
    experiment = client.get_experiment_by_name(experiment_name)
    if experiment is None:
        logger.error("MLflow experiment %s does not exist at %s", experiment_name, tracking_uri)
        return 1
    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string="attributes.status = 'FINISHED'",
        max_results=10000,
    )
    best = choose_best_run(runs)
    run_id = best.info.run_id
    model = mlflow.sklearn.load_model(f"runs:/{run_id}/model")
    models_dir.mkdir(parents=True, exist_ok=True)
    model_path = models_dir / "model.pkl"
    joblib.dump(model, model_path)

    evaluate_path = metrics_dir / "metrics.json"
    evaluate_best = None
    if evaluate_path.is_file():
        evaluate_best = json.loads(evaluate_path.read_text(encoding="utf-8")).get("best_run_id")
        if evaluate_best and evaluate_best != run_id:
            logger.warning(
                "MLflow best run %s differs from evaluate best run %s; promoting the MLflow run",
                run_id,
                evaluate_best,
            )

    bundle_features: list[str] = []
    preprocessor_path = models_dir / "preprocessor.joblib"
    if preprocessor_path.is_file():
        bundle = joblib.load(preprocessor_path)
        bundle_features = [str(name) for name in bundle.get("feature_names", [])]

    tags = best.data.tags
    meta = {
        "model_name": tags.get("model_family", best.data.params.get("model_family", "unknown")),
        "run_id": run_id,
        "run_name": best.info.run_name,
        "params": dict(best.data.params),
        "metrics": {
            "train_rmse": _metric(best, "train_rmse"),
            "train_mae": _metric(best, "train_mae"),
            "train_r2": _metric(best, "train_r2"),
            "test_rmse": _metric(best, "test_rmse"),
            "test_mae": _metric(best, "test_mae"),
            "test_r2": _metric(best, "test_r2"),
        },
        "feature_list": _feature_list(run_id, bundle_features),
        "git_commit": tags.get("git_commit", "unknown"),
        "git_dirty": tags.get("git_dirty", "unknown"),
        "dvc_data_hash": tags.get("dvc_data_hash", "unknown"),
        "timestamp": datetime.now(UTC).isoformat(),
        "selection_metric": "test_rmse",
        "experiment_name": experiment_name,
        "tracking_uri": tracking_uri,
        "preprocessor": "models/preprocessor.joblib",
        "evaluate_best_run_id": evaluate_best,
    }
    dump_json(models_dir / "model_meta.json", meta)
    logger.info(
        "promoted %s run %s test_rmse=%.4f to %s",
        meta["model_name"],
        run_id,
        meta["metrics"]["test_rmse"],
        model_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
