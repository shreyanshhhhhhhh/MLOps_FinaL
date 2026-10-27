"""API tests against a tiny falling-demand model. They never load models/model.pkl."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.metrics import METRICS
from app.model_loader import SERVICE
from src.features import add_engineered_features, fit_preprocessor, model_columns


class FallingDemand:
    """Demand falls as the scaled unit price rises, so elasticity is negative."""

    def predict(self, frame):
        price = frame["num__unit_price"].to_numpy()
        return 80.0 - 25.0 * price


def _context() -> dict:
    return {
        "product_category_name": "bed_bath_table",
        "freight_price": 10.0,
        "product_weight_g": 350,
        "product_score": 4.0,
        "weekday": 23,
        "weekend": 8,
        "holiday": 3,
        "month": 5,
        "year": 2018,
        "volume": 3800,
        "s": 10.2,
        "comp_1": 80.0,
        "comp_2": 40.0,
        "comp_3": 40.0,
        "ps1": 3.9,
        "ps2": 4.0,
        "ps3": 4.0,
        "fp1": 16.0,
        "fp2": 10.0,
        "fp3": 10.0,
        "lag_price": 40.0,
        "product_name_lenght": 39,
        "product_description_lenght": 161,
        "product_photos_qty": 2,
    }


def _training_frame():
    import pandas as pd

    low = _context() | {"unit_price": 20.0, "qty": 50}
    high = _context() | {"unit_price": 60.0, "qty": 10}
    other = _context() | {
        "unit_price": 40.0,
        "qty": 20,
        "product_category_name": "health_beauty",
    }
    frame = pd.DataFrame([low, high, other])
    return add_engineered_features(frame, ["comp_1", "comp_2", "comp_3"])


@pytest.fixture()
def client():
    METRICS.reset()
    SERVICE.reset()
    with TestClient(app) as test_client:
        yield test_client
    SERVICE.reset()
    METRICS.reset()


@pytest.fixture()
def loaded(client: TestClient) -> TestClient:
    frame = _training_frame()
    numeric, categorical = model_columns(
        {
            "categorical": ["product_category_name"],
            "base_numeric": [
                "unit_price",
                "freight_price",
                "product_weight_g",
                "product_score",
                "weekday",
                "weekend",
                "holiday",
                "month",
                "year",
                "volume",
                "s",
                "comp_1",
                "comp_2",
                "comp_3",
                "ps1",
                "ps2",
                "ps3",
                "fp1",
                "fp2",
                "fp3",
                "lag_price",
                "product_name_lenght",
                "product_description_lenght",
                "product_photos_qty",
            ],
            "engineered_numeric": [
                "comp_mean_price",
                "price_vs_comp",
                "price_change",
                "log_unit_price",
                "log_comp_mean",
            ],
            "excluded_from_model": ["qty", "log_qty"],
        }
    )
    bundle = fit_preprocessor(frame, numeric, categorical)
    SERVICE.install_for_tests(
        FallingDemand(),
        bundle,
        {
            "model_name": "dummy_falling",
            "metrics": {"test_rmse": 1.0, "test_mae": 0.5, "test_r2": 0.9},
            "git_commit": "test",
            "dvc_data_hash": "abc",
        },
    )
    return client


def test_health_is_up_when_model_is_missing(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_is_503_until_the_model_loads(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_ready_and_model_info_when_loaded(loaded: TestClient) -> None:
    ready = loaded.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    info = loaded.get("/model-info")
    assert info.status_code == 200
    body = info.json()
    assert body["model_name"] == "dummy_falling"
    assert body["git_commit"] == "test"
    assert body["dvc_data_hash"] == "abc"
    assert body["metrics"]["test_rmse"] == 1.0
    assert body["load_time"]


def test_predict_rejects_non_positive_price(loaded: TestClient) -> None:
    response = loaded.post("/predict-demand", json=_context() | {"unit_price": 0})
    assert response.status_code == 422


def test_optimize_rejects_inverted_range(loaded: TestClient) -> None:
    response = loaded.post(
        "/optimize-price",
        json=_context() | {"min_price": 50, "max_price": 20, "step": 5},
    )
    assert response.status_code == 422
    assert "min_price" in response.text


def test_optimize_returns_a_price_inside_the_range_and_negative_elasticity(
    loaded: TestClient,
) -> None:
    response = loaded.post(
        "/optimize-price",
        json=_context() | {"min_price": 20, "max_price": 80, "step": 5, "unit_cost": 10},
    )
    assert response.status_code == 200
    body = response.json()
    assert 20 <= body["best_price"] <= 80
    assert body["objective"] == "profit"
    assert body["expected_profit"] is not None
    assert body["curve"]
    assert body["curve"][0]["price"] == 20
    assert body["curve"][-1]["price"] == 80
    assert body["elasticity"] is not None
    assert body["elasticity"] < 0
    assert body["log_log_slope"] is not None
    assert body["log_log_slope"] < 0
    prices = [point["price"] for point in body["curve"]]
    assert prices == sorted(prices)


def test_predict_uses_the_training_feature_function(loaded: TestClient, monkeypatch) -> None:
    calls: list[str] = []
    from app import model_loader

    original = model_loader.add_engineered_features

    def wrapped(*args, **kwargs):
        calls.append("add_engineered_features")
        assert kwargs.get("target_column") is None
        return original(*args, **kwargs)

    monkeypatch.setattr(model_loader, "add_engineered_features", wrapped)
    response = loaded.post("/predict-demand", json=_context() | {"unit_price": 40})
    assert response.status_code == 200
    assert response.json()["predicted_qty"] >= 0
    assert calls == ["add_engineered_features"]


def test_metrics_count_requests_and_predictions(loaded: TestClient) -> None:
    loaded.post("/predict-demand", json=_context() | {"unit_price": 40})
    text = loaded.get("/metrics").text
    assert "priceoptima_requests_total" in text
    assert "priceoptima_request_latency_seconds_bucket" in text
    assert "priceoptima_predictions_total" in text
    assert "priceoptima_predictions_total 0" not in text
