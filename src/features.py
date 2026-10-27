"""Engineer price features and fit the train-only preprocessor."""

from __future__ import annotations

import logging
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.config import load_params, project_root, resolve_path
from src.provenance import configure_logging

logger = logging.getLogger(__name__)


def add_engineered_features(
    df: pd.DataFrame,
    competitor_price_columns: list[str],
    *,
    price_column: str = "unit_price",
    lag_column: str = "lag_price",
    target_column: str = "qty",
) -> pd.DataFrame:
    """Add relative-price features and log transforms.

    ``log_qty`` is stored for the Phase 2 elasticity work. It is a transform
    of the target, so ``excluded_from_model`` keeps it out of X.
    Ratios with a non-positive denominator become missing and are imputed
    from the training median later, rather than filled with a magic zero.
    """
    missing = [
        column
        for column in [price_column, lag_column, target_column, *competitor_price_columns]
        if column not in df.columns
    ]
    if missing:
        raise ValueError(f"feature engineering missing columns: {missing}")
    out = df.copy()
    price = pd.to_numeric(out[price_column], errors="coerce")
    lag = pd.to_numeric(out[lag_column], errors="coerce")
    comp = out[competitor_price_columns].apply(pd.to_numeric, errors="coerce")
    comp_mean = comp.mean(axis=1)
    out["comp_mean_price"] = comp_mean
    out["price_vs_comp"] = price / comp_mean.where(comp_mean > 0)
    out["price_change"] = (price - lag) / lag.where(lag > 0)
    out["log_unit_price"] = np.log1p(price.clip(lower=0))
    out["log_comp_mean"] = np.log1p(comp_mean.clip(lower=0))
    target = pd.to_numeric(out[target_column], errors="coerce")
    out["log_qty"] = np.log1p(target.clip(lower=0))
    return out


def model_columns(features_cfg: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return numeric and categorical columns that are allowed into the model.

    A column listed as both an input and an exclusion is a config error.
    That check is what stops total_price or log_qty being added later
    without an explicit decision.
    """
    numeric = list(features_cfg["base_numeric"]) + list(features_cfg["engineered_numeric"])
    categorical = list(features_cfg["categorical"])
    excluded = set(features_cfg["excluded_from_model"])
    overlap = sorted((set(numeric) | set(categorical)) & excluded)
    if overlap:
        raise ValueError(f"columns cannot be both model inputs and excluded: {overlap}")
    if len(numeric) != len(set(numeric)):
        raise ValueError("base_numeric and engineered_numeric overlap")
    return numeric, categorical


def build_preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    """Median impute and scale numerics. One-hot encode categories.

    ``handle_unknown='ignore'`` keeps a new category in the test month from
    crashing scoring. Unknown levels become zeros, which is the train-fit
    encoding with no extra column learned from the test set.
    """
    numeric_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("num", numeric_pipe, numeric),
            ("cat", categorical_pipe, categorical),
        ],
        remainder="drop",
    )


def fit_preprocessor(
    train: pd.DataFrame,
    numeric: list[str],
    categorical: list[str],
) -> dict[str, Any]:
    """Fit the preprocessor on train and return a joblib-ready bundle."""
    columns = numeric + categorical
    missing = [column for column in columns if column not in train.columns]
    if missing:
        raise ValueError(f"train frame missing model columns: {missing}")
    preprocessor = build_preprocessor(numeric, categorical)
    preprocessor.fit(train[columns])
    feature_names = [str(name) for name in preprocessor.get_feature_names_out()]
    return {
        "preprocessor": preprocessor,
        "numeric_columns": numeric,
        "categorical_columns": categorical,
        "feature_names": feature_names,
    }


def transform_frame(bundle: dict[str, Any], df: pd.DataFrame) -> pd.DataFrame:
    """Apply a fitted bundle. This never refits."""
    columns = list(bundle["numeric_columns"]) + list(bundle["categorical_columns"])
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"frame missing model columns: {missing}")
    transformed = bundle["preprocessor"].transform(df[columns])
    return pd.DataFrame(transformed, columns=list(bundle["feature_names"]), index=df.index)


def main() -> int:
    """Run the features stage from params.yaml."""
    configure_logging()
    params = load_params()
    root = project_root()
    features_cfg = params["features"]
    processed_dir = resolve_path(root, params["paths"]["processed_dir"])
    models_dir = resolve_path(root, params["paths"]["models_dir"])
    train = pd.read_csv(processed_dir / "train.csv")
    test = pd.read_csv(processed_dir / "test.csv")
    competitor_columns = list(features_cfg["competitor_price_columns"])
    train = add_engineered_features(
        train,
        competitor_columns,
        price_column=features_cfg["price_column"],
        lag_column=features_cfg["lag_column"],
        target_column=features_cfg["target"],
    )
    test = add_engineered_features(
        test,
        competitor_columns,
        price_column=features_cfg["price_column"],
        lag_column=features_cfg["lag_column"],
        target_column=features_cfg["target"],
    )
    numeric, categorical = model_columns(features_cfg)
    bundle = fit_preprocessor(train, numeric, categorical)
    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, models_dir / "preprocessor.joblib")
    train.to_csv(processed_dir / "train_features.csv", index=False)
    test.to_csv(processed_dir / "test_features.csv", index=False)
    logger.info("fitted preprocessor with %s model columns", len(bundle["feature_names"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
