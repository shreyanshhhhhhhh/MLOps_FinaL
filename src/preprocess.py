"""Clean the raw panel and cut a chronological train/test split."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import load_params, project_root, resolve_path
from src.provenance import configure_logging, dump_json

logger = logging.getLogger(__name__)


def parse_month_year(df: pd.DataFrame, column: str, date_format: str) -> pd.DataFrame:
    """Parse month_year and drop rows whose dates do not match the format.

    The file uses day-month-year with the day fixed at 01. Parsing with an
    explicit format keeps 01-05-2017 as May 2017 rather than 5 January.
    """
    out = df.copy()
    parsed = pd.to_datetime(out[column], format=date_format, errors="coerce")
    invalid = int(parsed.isna().sum())
    if invalid:
        logger.warning("dropping %s rows with unparseable %s", invalid, column)
    out = out.loc[parsed.notna()].copy()
    out[column] = parsed.loc[parsed.notna()]
    return out


def chronological_split(
    df: pd.DataFrame,
    date_column: str,
    test_size: float,
) -> tuple[pd.DataFrame, pd.DataFrame, list[pd.Timestamp], list[pd.Timestamp]]:
    """Hold out the last fraction of distinct months.

    The cut is on the month, not the row. A product-month is never split
    across train and test, and no future month is used to fit the model.
    ``test_size`` is a fraction of the month axis. With 20 months and 0.2
    the test set is the last 4 months.
    """
    months = sorted(pd.to_datetime(df[date_column].dropna().unique()))
    if len(months) < 2:
        raise ValueError("need at least two distinct months to split")
    n_test = int(round(len(months) * test_size))
    n_test = min(max(n_test, 1), len(months) - 1)
    test_months = months[-n_test:]
    train_months = months[:-n_test]
    test_set = set(test_months)
    test_mask = df[date_column].isin(test_set)
    train = df.loc[~test_mask].copy()
    test = df.loc[test_mask].copy()
    if train.empty or test.empty:
        raise ValueError("chronological split produced an empty partition")
    return train, test, train_months, test_months


def fit_iqr_fences(
    train: pd.DataFrame,
    columns: list[str],
    factor: float,
) -> dict[str, dict[str, float]]:
    """Tukey fences from the training period only.

    A constant column has IQR 0. In that case the fence is the train min and
    max, so a wild test value is still clipped to the range actually seen
    in training and cannot widen the fence.
    """
    if factor <= 0:
        raise ValueError("iqr_factor must be positive")
    fences: dict[str, dict[str, float]] = {}
    for column in columns:
        series = pd.to_numeric(train[column], errors="coerce").dropna()
        if series.empty:
            raise ValueError(f"cannot fit an IQR fence on empty column {column}")
        q1 = float(series.quantile(0.25))
        q3 = float(series.quantile(0.75))
        iqr = q3 - q1
        if iqr == 0:
            low, high = float(series.min()), float(series.max())
        else:
            low = q1 - factor * iqr
            high = q3 + factor * iqr
        fences[column] = {"low": low, "high": high, "q1": q1, "q3": q3}
    return fences


def apply_fences(df: pd.DataFrame, fences: dict[str, dict[str, float]]) -> pd.DataFrame:
    """Clip columns to training fences. Rows are kept so the panel stays complete."""
    out = df.copy()
    for column, fence in fences.items():
        out[column] = pd.to_numeric(out[column], errors="coerce").clip(fence["low"], fence["high"])
    return out


def _require_columns(df: pd.DataFrame, columns: list[str], context: str) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"{context} missing columns: {missing}")


def _as_month_strings(months: list[pd.Timestamp]) -> list[str]:
    return [pd.Timestamp(month).strftime("%Y-%m-%d") for month in months]


def preprocess_frame(
    df: pd.DataFrame,
    *,
    date_column: str,
    date_format: str,
    target: str,
    test_size: float,
    outlier_columns: list[str],
    iqr_factor: float,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Parse dates, drop rows without a target, split, then clip outliers.

    Fences are fit after the split and only on train. Fitting them on the
    full panel would let test-set extremes decide the clip thresholds.
    """
    _require_columns(df, [date_column, target, *outlier_columns], "preprocess")
    rows_input = int(len(df))
    parsed = parse_month_year(df, date_column, date_format)
    dropped_dates = rows_input - int(len(parsed))
    target_numeric = pd.to_numeric(parsed[target], errors="coerce")
    missing_target = int(target_numeric.isna().sum())
    if missing_target:
        logger.warning("dropping %s rows with missing %s", missing_target, target)
    cleaned = parsed.loc[target_numeric.notna()].copy()
    cleaned[target] = target_numeric.loc[target_numeric.notna()].astype(float)
    sort_columns = [date_column]
    if "product_id" in cleaned.columns:
        sort_columns.append("product_id")
    cleaned = cleaned.sort_values(sort_columns).reset_index(drop=True)

    train, test, train_months, test_months = chronological_split(cleaned, date_column, test_size)
    fences = fit_iqr_fences(train, outlier_columns, iqr_factor)
    train = apply_fences(train, fences).reset_index(drop=True)
    test = apply_fences(test, fences).reset_index(drop=True)
    meta: dict[str, Any] = {
        "rows_input": rows_input,
        "rows_dropped_invalid_date": dropped_dates,
        "rows_dropped_missing_target": missing_target,
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "n_months_train": len(train_months),
        "n_months_test": len(test_months),
        "train_months": _as_month_strings(train_months),
        "test_months": _as_month_strings(test_months),
        "test_size": test_size,
        "strategy": "chronological",
        "seed": seed,
        "iqr_factor": iqr_factor,
        "fences": fences,
    }
    logger.info(
        "split train=%s test=%s test_months=%s",
        meta["n_train"],
        meta["n_test"],
        meta["test_months"],
    )
    return train, test, meta


def _write_split(df: pd.DataFrame, path: Path, date_column: str) -> None:
    out = df.copy()
    out[date_column] = pd.to_datetime(out[date_column]).dt.strftime("%Y-%m-%d")
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)


def main() -> int:
    """Run the preprocess stage from params.yaml."""
    configure_logging()
    params = load_params()
    root = project_root()
    prep = params["preprocess"]
    raw_path = resolve_path(root, params["paths"]["raw_csv"])
    processed_dir = resolve_path(root, params["paths"]["processed_dir"])
    if not raw_path.is_file():
        logger.error("raw csv not found at %s", raw_path)
        return 1
    frame = pd.read_csv(raw_path)
    train, test, meta = preprocess_frame(
        frame,
        date_column=prep["date_column"],
        date_format=prep["date_format"],
        target=prep["target"],
        test_size=float(params["split"]["test_size"]),
        outlier_columns=list(prep["outlier_columns"]),
        iqr_factor=float(prep["iqr_factor"]),
        seed=int(params["seed"]),
    )
    _write_split(train, processed_dir / "train.csv", prep["date_column"])
    _write_split(test, processed_dir / "test.csv", prep["date_column"])
    dump_json(processed_dir / "preprocess_meta.json", meta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
