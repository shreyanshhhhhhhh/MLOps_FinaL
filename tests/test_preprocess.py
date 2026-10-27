"""Schema and calendar parsing of the preprocess stage."""

from __future__ import annotations

import pandas as pd

from src.preprocess import parse_month_year, preprocess_frame
from tests.conftest import RAW_COLUMNS

PREPROCESS_KWARGS = {
    "date_column": "month_year",
    "date_format": "%d-%m-%Y",
    "target": "qty",
    "test_size": 0.2,
    "outlier_columns": ["qty", "unit_price", "freight_price", "lag_price"],
    "iqr_factor": 1.5,
    "seed": 42,
}


def test_day_month_year_parses_to_may_not_january() -> None:
    frame = pd.DataFrame({"month_year": ["01-05-2017"], "qty": [1]})
    parsed = parse_month_year(frame, "month_year", "%d-%m-%Y")
    assert parsed["month_year"].iloc[0] == pd.Timestamp("2017-05-01")


def test_preprocess_output_schema(panel: pd.DataFrame) -> None:
    train, test, meta = preprocess_frame(panel, **PREPROCESS_KWARGS)

    assert list(train.columns) == RAW_COLUMNS
    assert list(test.columns) == RAW_COLUMNS
    assert pd.api.types.is_datetime64_any_dtype(train["month_year"])
    assert pd.api.types.is_datetime64_any_dtype(test["month_year"])
    assert pd.api.types.is_numeric_dtype(train["qty"])
    assert pd.api.types.is_numeric_dtype(test["qty"])
    assert train["qty"].notna().all()
    assert test["qty"].notna().all()
    assert train["month_year"].notna().all()
    assert test["month_year"].notna().all()
    assert len(train) + len(test) == len(panel)
    assert meta["n_train"] == len(train)
    assert meta["n_test"] == len(test)
    assert meta["strategy"] == "chronological"
    # Last of five months at test_size 0.2. Lexical order would have kept Dec 2017.
    assert meta["test_months"] == ["2018-03-01"]
    assert meta["train_months"][0] == "2017-11-01"
    assert "2018-01-01" in meta["train_months"]
