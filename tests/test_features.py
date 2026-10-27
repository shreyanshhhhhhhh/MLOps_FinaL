"""Feature engineering on a hand-checked fixture."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.features import add_engineered_features, model_columns


def test_price_ratio_change_and_logs_on_fixture() -> None:
    frame = pd.DataFrame(
        {
            "unit_price": [10.0],
            "lag_price": [8.0],
            "qty": [4.0],
            "comp_1": [8.0],
            "comp_2": [10.0],
            "comp_3": [12.0],
        }
    )
    engineered = add_engineered_features(frame, ["comp_1", "comp_2", "comp_3"])

    assert engineered["comp_mean_price"].iloc[0] == pytest.approx(10.0)
    assert engineered["price_vs_comp"].iloc[0] == pytest.approx(1.0)
    assert engineered["price_change"].iloc[0] == pytest.approx((10.0 - 8.0) / 8.0)
    assert engineered["log_unit_price"].iloc[0] == pytest.approx(np.log1p(10.0))
    assert engineered["log_comp_mean"].iloc[0] == pytest.approx(np.log1p(10.0))
    assert engineered["log_qty"].iloc[0] == pytest.approx(np.log1p(4.0))


def test_inference_path_skips_target_and_keeps_price_features() -> None:
    frame = pd.DataFrame(
        {
            "unit_price": [10.0],
            "lag_price": [8.0],
            "comp_1": [8.0],
            "comp_2": [10.0],
            "comp_3": [12.0],
        }
    )
    engineered = add_engineered_features(frame, ["comp_1", "comp_2", "comp_3"], target_column=None)
    assert "log_qty" not in engineered.columns
    assert engineered["price_vs_comp"].iloc[0] == pytest.approx(1.0)
    assert engineered["log_unit_price"].iloc[0] == pytest.approx(np.log1p(10.0))


def test_non_positive_denominator_becomes_missing() -> None:
    frame = pd.DataFrame(
        {
            "unit_price": [10.0, 10.0],
            "lag_price": [0.0, 5.0],
            "qty": [1.0, 1.0],
            "comp_1": [0.0, 4.0],
            "comp_2": [0.0, 6.0],
            "comp_3": [0.0, 5.0],
        }
    )
    engineered = add_engineered_features(frame, ["comp_1", "comp_2", "comp_3"])
    assert pd.isna(engineered["price_vs_comp"].iloc[0])
    assert pd.isna(engineered["price_change"].iloc[0])
    assert engineered["price_vs_comp"].iloc[1] == pytest.approx(10.0 / 5.0)
    assert engineered["price_change"].iloc[1] == pytest.approx(1.0)


def test_excluded_columns_cannot_also_be_inputs() -> None:
    features = {
        "base_numeric": ["unit_price", "qty"],
        "engineered_numeric": ["log_unit_price"],
        "categorical": ["product_category_name"],
        "excluded_from_model": ["qty", "log_qty"],
    }
    with pytest.raises(ValueError, match="qty"):
        model_columns(features)
