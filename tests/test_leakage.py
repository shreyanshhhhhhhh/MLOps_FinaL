"""Guards for future-month leakage and test-set statistics leaking into fit."""

from __future__ import annotations

import pandas as pd
import pytest

from src.config import load_params
from src.features import add_engineered_features, fit_preprocessor, model_columns, transform_frame
from src.preprocess import fit_iqr_fences, preprocess_frame
from tests.test_preprocess import PREPROCESS_KWARGS


def test_train_months_are_strictly_before_test_months(panel: pd.DataFrame) -> None:
    train, test, meta = preprocess_frame(panel, **PREPROCESS_KWARGS)

    train_months = set(train["month_year"])
    test_months = set(test["month_year"])
    assert train_months.isdisjoint(test_months)
    assert train["month_year"].max() < test["month_year"].min()
    assert meta["test_months"] == ["2018-03-01"]

    train_keys = set(zip(train["product_id"], train["month_year"], strict=True))
    test_keys = set(zip(test["product_id"], test["month_year"], strict=True))
    assert train_keys.isdisjoint(test_keys)


def test_outlier_fences_ignore_test_extremes(panel: pd.DataFrame) -> None:
    poisoned = panel.copy()
    poisoned.loc[poisoned["month_year"] == "01-03-2018", "qty"] = 10_000
    train, test, meta = preprocess_frame(poisoned, **PREPROCESS_KWARGS)

    high = meta["fences"]["qty"]["high"]
    assert high < 100
    assert test["qty"].max() == pytest.approx(high)
    assert train["qty"].max() <= high + 1e-9

    # Refit on the clipped train. The threshold must match the one stored at split time.
    refit = fit_iqr_fences(train, ["qty"], 1.5)
    assert refit["qty"]["high"] == pytest.approx(high)


def test_scaler_and_encoder_fit_on_train_only() -> None:
    params = load_params()
    features = params["features"]
    numeric, categorical = model_columns(features)
    banned = ("log_qty", "total_price", "customers", "product_id", "qty")

    def filled(price: float, category: str, rows: int) -> pd.DataFrame:
        data: dict[str, list] = {}
        present = set(features["base_numeric"]) | set(categorical) | set(banned)
        for column in present:
            if column == "product_category_name":
                data[column] = [category] * rows
            elif column == "product_id":
                data[column] = [f"p{i}" for i in range(rows)]
            elif column == "month_year":
                data[column] = ["2017-01-01"] * rows
            elif column == "unit_price":
                data[column] = [price] * rows
            elif column in {"comp_1", "comp_2", "comp_3", "lag_price"}:
                data[column] = [10.0] * rows
            elif column == "qty":
                data[column] = [5.0] * rows
            else:
                data[column] = [1.0] * rows
        return pd.DataFrame(data)

    train = add_engineered_features(
        filled(10.0, "bed_bath_table", 6),
        list(features["competitor_price_columns"]),
    )
    test = add_engineered_features(
        filled(1000.0, "unseen_category", 6),
        list(features["competitor_price_columns"]),
    )
    bundle = fit_preprocessor(train, numeric, categorical)
    for column in banned:
        assert column not in bundle["numeric_columns"]
        assert column not in bundle["categorical_columns"]
        assert f"num__{column}" not in bundle["feature_names"]

    scaler = bundle["preprocessor"].named_transformers_["num"].named_steps["scaler"]
    price_index = numeric.index("unit_price")
    assert scaler.mean_[price_index] == pytest.approx(10.0)
    pooled = pd.concat([train["unit_price"], test["unit_price"]], ignore_index=True).mean()
    assert scaler.mean_[price_index] != pytest.approx(pooled)

    transformed_train = transform_frame(bundle, train)
    transformed_test = transform_frame(bundle, test)
    assert list(transformed_train.columns) == bundle["feature_names"]
    assert list(transformed_test.columns) == bundle["feature_names"]
    assert transformed_train.iloc[:, price_index].mean() == pytest.approx(0.0, abs=1e-6)
    assert transformed_test.iloc[0, price_index] > 10
