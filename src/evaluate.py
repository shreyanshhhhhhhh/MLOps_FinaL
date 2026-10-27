"""Recompute test metrics and write the predicted-vs-actual plots."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import mlflow
import numpy as np

from src.config import load_params, project_root, resolve_path
from src.provenance import configure_logging, dump_json
from src.scoring import regression_metrics

logger = logging.getLogger(__name__)


def save_diagnostic_plots(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    metrics_dir: Path,
    title_suffix: str,
) -> None:
    """Write predicted-vs-actual and residual plots for the selected run."""
    metrics_dir.mkdir(parents=True, exist_ok=True)
    actual = np.asarray(y_true, dtype=float)
    predicted = np.asarray(y_pred, dtype=float)

    figure, axis = plt.subplots(figsize=(6, 6))
    axis.scatter(actual, predicted, alpha=0.75, edgecolors="none")
    lower = float(min(actual.min(), predicted.min()))
    upper = float(max(actual.max(), predicted.max()))
    axis.plot([lower, upper], [lower, upper], color="black", linewidth=1)
    axis.set_xlabel("Actual qty")
    axis.set_ylabel("Predicted qty")
    axis.set_title(f"Predicted vs actual ({title_suffix})")
    figure.tight_layout()
    figure.savefig(metrics_dir / "pred_vs_actual.png", dpi=120)
    plt.close(figure)

    residuals = actual - predicted
    figure, axis = plt.subplots(figsize=(6, 4))
    axis.scatter(predicted, residuals, alpha=0.75, edgecolors="none")
    axis.axhline(0.0, color="black", linewidth=1)
    axis.set_xlabel("Predicted qty")
    axis.set_ylabel("Residual (actual - predicted)")
    axis.set_title(f"Residuals ({title_suffix})")
    figure.tight_layout()
    figure.savefig(metrics_dir / "residuals.png", dpi=120)
    plt.close(figure)


def main() -> int:
    """Score every logged run on the held-out months and write metrics.json."""
    configure_logging()
    params = load_params()
    root = project_root()
    metrics_dir = resolve_path(root, params["paths"]["metrics_dir"])
    summary_path = metrics_dir / "train_runs.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    mlflow.set_tracking_uri(summary["tracking_uri"])

    # The matrix was transformed in train with the fitted preprocessor.
    # Evaluate does not open the feature files, so the DVC graph stays linear.
    evaluation = joblib.load(metrics_dir / "eval_bundle.joblib")
    X_test = evaluation["X_test"]
    y_test = np.asarray(evaluation["y_test"], dtype=float)

    scored: list[dict] = []
    predictions: dict[str, np.ndarray] = {}
    for run in summary["runs"]:
        model = mlflow.sklearn.load_model(f"runs:/{run['run_id']}/model")
        predicted = np.asarray(model.predict(X_test), dtype=float)
        metrics = regression_metrics(y_test, predicted)
        logged_rmse = float(run["test_rmse"])
        if abs(logged_rmse - metrics["rmse"]) > 1e-6:
            logger.warning(
                "run %s logged test_rmse %.6f but evaluate recomputed %.6f",
                run["run_id"],
                logged_rmse,
                metrics["rmse"],
            )
        record = {
            "run_id": run["run_id"],
            "run_name": run["run_name"],
            "model_family": run["model_family"],
            "params": run["params"],
            "train_rmse": run["train_rmse"],
            "train_mae": run["train_mae"],
            "train_r2": run["train_r2"],
            "test_rmse": metrics["rmse"],
            "test_mae": metrics["mae"],
            "test_r2": metrics["r2"],
        }
        scored.append(record)
        predictions[run["run_id"]] = predicted

    scored.sort(key=lambda record: (record["test_rmse"], record["run_id"]))
    best = scored[0]
    save_diagnostic_plots(
        y_test,
        predictions[best["run_id"]],
        metrics_dir,
        title_suffix=best["run_name"],
    )
    dump_json(
        metrics_dir / "metrics.json",
        {
            "selection_metric": "test_rmse",
            "n_runs": len(scored),
            "best_run_id": best["run_id"],
            "best_model_family": best["model_family"],
            "best_test_rmse": best["test_rmse"],
            "runs": scored,
        },
    )
    logger.info(
        "best run %s family=%s test_rmse=%.4f",
        best["run_id"],
        best["model_family"],
        best["test_rmse"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
