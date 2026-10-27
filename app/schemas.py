"""Request and response models. Field names match the training columns."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, Field, model_validator

MAX_GRID_POINTS = 500


class ProductContext(BaseModel):
    """Context features that do not include the price being scored.

    ``product_name_lenght`` and ``product_description_lenght`` keep the
    spelling from retail_price.csv so the serving frame matches training.
    """

    product_category_name: str = Field(min_length=1, max_length=80)
    freight_price: float = Field(ge=0, le=100_000)
    product_weight_g: float = Field(ge=0, le=100_000)
    product_score: float = Field(ge=0, le=5)
    weekday: int = Field(ge=0, le=31)
    weekend: int = Field(ge=0, le=31)
    holiday: int = Field(ge=0, le=31)
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)
    volume: float = Field(ge=0, le=1_000_000)
    s: float = Field(ge=0, le=1_000)
    comp_1: float = Field(gt=0, le=1_000_000)
    comp_2: float = Field(gt=0, le=1_000_000)
    comp_3: float = Field(gt=0, le=1_000_000)
    ps1: float = Field(ge=0, le=5)
    ps2: float = Field(ge=0, le=5)
    ps3: float = Field(ge=0, le=5)
    fp1: float = Field(ge=0, le=100_000)
    fp2: float = Field(ge=0, le=100_000)
    fp3: float = Field(ge=0, le=100_000)
    lag_price: float = Field(gt=0, le=1_000_000)
    product_name_lenght: int = Field(ge=0, le=500)
    product_description_lenght: int = Field(ge=0, le=20_000)
    product_photos_qty: int = Field(ge=0, le=50)


class PredictRequest(ProductContext):
    unit_price: float = Field(gt=0, le=1_000_000)


class OptimizeRequest(ProductContext):
    min_price: float = Field(gt=0, le=1_000_000)
    max_price: float = Field(gt=0, le=1_000_000)
    step: float = Field(gt=0, le=100_000)
    unit_cost: float | None = Field(default=None, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def check_price_grid(self) -> Self:
        if self.min_price >= self.max_price:
            raise ValueError("min_price must be less than max_price")
        points = int((self.max_price - self.min_price) / self.step) + 1
        if points < 2:
            raise ValueError("price grid must contain at least 2 prices")
        if points > MAX_GRID_POINTS:
            raise ValueError(
                f"price grid has {points} points; the maximum is {MAX_GRID_POINTS}. Increase step"
            )
        return self


class PredictResponse(BaseModel):
    predicted_qty: float
    model_output: float
    unit_price: float


class CurvePoint(BaseModel):
    price: float
    predicted_qty: float
    revenue: float
    profit: float | None


class OptimizeResponse(BaseModel):
    best_price: float
    expected_demand: float
    expected_revenue: float
    expected_profit: float | None
    objective: str
    elasticity: float | None
    elasticity_method: str
    log_log_slope: float | None
    curve: list[CurvePoint]


class ModelInfo(BaseModel):
    model_name: str
    metrics: dict[str, float | None]
    git_commit: str
    dvc_data_hash: str
    load_time: str
    model_version: str | None = None
