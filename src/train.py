"""Train the params.yaml grid and log every run to the local MLflow store."""

from __future__ import annotations

import itertools
import logging
from typing import Any

import joblib
import mlflow
import pandas as pd
from lightgbm import LGBMRegressor
from mlflow.models.signature import infer_signature
from sklearn.base import BaseEstimator
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression, Ridge

from src.config import load_params, project_root, resolve_path
from src.features import transform_frame
from src.provenance import configure_logging, dump_json, dvc_data_hash, git_commit, git_dirty
from src.scoring import regression_metrics

logger = logging.getLogger(__name__)

# MLflow 3 saves sklearn estimators with skops and refuses types it did not
# review. These are the objects this process has just fit, not downloaded files.
SKOPS_TRUSTED_TYPES = [
    "sklearn.tree._tree.Tree",
    "collections.OrderedDict",
    "lightgbm.basic.Booster",
    "lightgbm.sklearn.LGBMRegressor",
]


def iter_model_configs(models: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Expand each family grid into concrete parameter dicts.

    The product is taken in YAML key order so the same params.yaml yields
    the same run sequence on every machine.
    """
    configs: list[tuple[str, dict[str, Any]]] = []
    for family, grid in models.items():
        if not grid:
            configs.append((family, {}))
            continue
        keys = list(grid)
        value_lists: list[list[Any]] = []
        for key in keys:
            value = grid[key]
            if isinstance(value, list):
                if not value:
                    raise ValueError(f"{family}.{key} has an empty grid")
                value_lists.append(list(value))
            else:
                value_lists.append([value])
        for combo in itertools.product(*value_lists):
            configs.append((family, dict(zip(keys, combo, strict=True))))
    return configs


def build_estimator(family: str, params: dict[str, Any], seed: int) -> BaseEstimator:
    """Construct one estimator. ``n_jobs=1`` keeps tree models deterministic."""
    if family == "linear_regression":
        return LinearRegression(**params)
    if family == "ridge":
        return Ridge(random_state=seed, **params)
    if family == "random_forest":
        return RandomForestRegressor(random_state=seed, n_jobs=1, **params)
    if family == "gradient_boosting":
        return GradientBoostingRegressor(random_state=seed, **params)
    if family == "lightgbm":
        return LGBMRegressor(random_state=seed, n_jobs=1, verbose=-1, **params)
    raise ValueError(f"unknown model family: {family}")


def _loggable_params(params: dict[str, Any]) -> dict[str, Any]:
    logged: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, bool):
            logged[key] = str(value).lower()
        elif isinstance(value, (int, float, str)):
            logged[key] = value
        else:
            logged[key] = str(value)
    return logged


def _run_name(family: str, params: dict[str, Any]) -> str:
    if not params:
        return family
    bits = [f"{key}={value}" for key, value in params.items()]
    return family + "|" + "|".join(bits)


def _configure_tracking(tracking_uri: str, experiment_name: str) -> None:
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)


def train_grid(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    configs: list[tuple[str, dict[str, Any]]],
    *,
    seed: int,
    tracking_uri: str,
    experiment_name: str,
    git_sha: str,
    data_hash: str,
    dirty: bool,
) -> list[dict[str, Any]]:
    """Fit every config, log it, and return a JSON-ready summary."""
    _configure_tracking(tracking_uri, experiment_name)
    feature_names = [str(column) for column in X_train.columns]
    summaries: list[dict[str, Any]] = []
    for family, params in configs:
        estimator = build_estimator(family, params, seed)
        run_name = _run_name(family, params)
        with mlflow.start_run(run_name=run_name):
            active = mlflow.active_run()
            if active is None:
                raise RuntimeError("MLflow did not open a run")
            run_id = active.info.run_id
            mlflow.set_tags(
                {
                    "git_commit": git_sha,
                    "dvc_data_hash": data_hash,
                    "git_dirty": str(dirty).lower(),
                    "model_family": family,
                    "project": "priceoptima",
                }
            )
            logged_params = _loggable_params(params)
            mlflow.log_params({"model_family": family, "seed": seed, **logged_params})
            mlflow.log_dict({"features": feature_names}, "feature_list.json")
            estimator.fit(X_train, y_train)
            train_pred = estimator.predict(X_train)
            test_pred = estimator.predict(X_test)
            train_scores = regression_metrics(y_train, train_pred)
            test_scores = regression_metrics(y_test, test_pred)
            mlflow.log_metrics(
                {
                    "train_rmse": train_scores["rmse"],
                    "train_mae": train_scores["mae"],
                    "train_r2": train_scores["r2"],
                    "test_rmse": test_scores["rmse"],
                    "test_mae": test_scores["mae"],
                    "test_r2": test_scores["r2"],
                }
            )
            signature = infer_signature(X_train, train_pred)
            mlflow.sklearn.log_model(
                estimator,
                name="model",
                signature=signature,
                input_example=X_train.head(2),
                skops_trusted_types=SKOPS_TRUSTED_TYPES,
            )
            logger.info(
                "run %s family=%s test_rmse=%.4f test_mae=%.4f test_r2=%.4f",
                run_id,
                family,
                test_scores["rmse"],
                test_scores["mae"],
                test_scores["r2"],
            )
            summaries.append(
                {
                    "run_id": run_id,
                    "run_name": run_name,
                    "model_family": family,
                    "params": logged_params,
                    "train_rmse": train_scores["rmse"],
                    "train_mae": train_scores["mae"],
                    "train_r2": train_scores["r2"],
                    "test_rmse": test_scores["rmse"],
                    "test_mae": test_scores["mae"],
                    "test_r2": test_scores["r2"],
                }
            )
    return summaries


def main() -> int:
    """Run the training sweep from params.yaml."""
    configure_logging()
    params = load_params()
    root = project_root()
    processed_dir = resolve_path(root, params["paths"]["processed_dir"])
    models_dir = resolve_path(root, params["paths"]["models_dir"])
    metrics_dir = resolve_path(root, params["paths"]["metrics_dir"])
    target = params["features"]["target"]
    bundle = joblib.load(models_dir / "preprocessor.joblib")
    train = pd.read_csv(processed_dir / "train_features.csv")
    test = pd.read_csv(processed_dir / "test_features.csv")
    X_train = transform_frame(bundle, train)
    X_test = transform_frame(bundle, test)
    y_train = pd.to_numeric(train[target], errors="raise")
    y_test = pd.to_numeric(test[target], errors="raise")
    configs = iter_model_configs(params["models"])
    if len(configs) < 12:
        logger.error("parameter grid produced %s runs; need at least 12", len(configs))
        return 1
    tracking_uri = str(resolve_path(root, params["tracking"]["tracking_uri"]))
    data_hash = dvc_data_hash(resolve_path(root, params["paths"]["dvc_file"]))
    joblib.dump(
        {
            "X_test": X_test,
            "y_test": y_test.to_numpy(),
            "feature_names": [str(column) for column in X_test.columns],
        },
        metrics_dir / "eval_bundle.joblib",
    )
    summaries = train_grid(
        X_train,
        y_train,
        X_test,
        y_test,
        configs,
        seed=int(params["seed"]),
        tracking_uri=tracking_uri,
        experiment_name=params["tracking"]["experiment_name"],
        git_sha=git_commit(root),
        data_hash=data_hash,
        dirty=git_dirty(root),
    )
    dump_json(
        metrics_dir / "train_runs.json",
        {
            "experiment_name": params["tracking"]["experiment_name"],
            "tracking_uri": tracking_uri,
            "git_commit": git_commit(root),
            "dvc_data_hash": data_hash,
            "n_runs": len(summaries),
            "feature_list": list(bundle["feature_names"]),
            "runs": summaries,
        },
    )
    logger.info("logged %s runs to %s", len(summaries), tracking_uri)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
