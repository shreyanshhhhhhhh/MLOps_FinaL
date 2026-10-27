"""PriceOptima serving API.

``/health`` only proves the process is up. ``/ready`` proves the model
artifacts have been loaded. A failed ``dvc pull`` keeps the process alive
so the orchestrator can tell those two states apart.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from app.logging_config import configure_logging
from app.metrics import METRICS
from app.model_loader import SERVICE
from app.pricing import optimize_price
from app.schemas import (
    ModelInfo,
    OptimizeRequest,
    OptimizeResponse,
    PredictRequest,
    PredictResponse,
)

logger = logging.getLogger("priceoptima")


class NotReady(Exception):
    """Raised when a scoring route is called before the artifacts are loaded."""

    def __init__(self, detail: str) -> None:
        self.detail = detail


def _require_model() -> None:
    if not SERVICE.ready:
        raise NotReady(SERVICE.error or "model is not loaded")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Start the disk watcher when the container is allowed to autoload."""
    configure_logging()
    if os.environ.get("MODEL_AUTOLOAD", "1") == "1":
        thread = threading.Thread(target=SERVICE.watch, name="model-watch", daemon=True)
        thread.start()
    yield


app = FastAPI(title="PriceOptima", version="0.2.0", lifespan=lifespan)


@app.exception_handler(NotReady)
async def not_ready_handler(_request: Request, exc: NotReady) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "detail": exc.detail},
    )


@app.middleware("http")
async def log_request(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        latency = time.perf_counter() - started
        METRICS.observe_request(request.url.path, 500, latency)
        logger.exception(
            "request failed",
            extra={
                "request_id": request_id,
                "endpoint": request.url.path,
                "method": request.method,
                "status": 500,
                "latency_ms": round(latency * 1000, 3),
            },
        )
        raise
    latency = time.perf_counter() - started
    METRICS.observe_request(request.url.path, response.status_code, latency)
    response.headers["x-request-id"] = request_id
    logger.info(
        "request",
        extra={
            "request_id": request_id,
            "endpoint": request.url.path,
            "method": request.method,
            "status": response.status_code,
            "latency_ms": round(latency * 1000, 3),
        },
    )
    return response


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness. This stays 200 even when the model fetch has not succeeded."""
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    """Readiness. 200 only after model.pkl, the preprocessor, and the card are loaded."""
    _require_model()
    return {"status": "ready"}


@app.get("/model-info", response_model=ModelInfo)
def model_info() -> ModelInfo:
    """Return the card written by select_best, plus the time this process loaded it."""
    _require_model()
    return SERVICE.info()


@app.post("/predict-demand", response_model=PredictResponse)
def predict_demand(body: PredictRequest) -> PredictResponse:
    """Predict quantity at one price. Features are built by src.features."""
    _require_model()
    context = body.model_dump(exclude={"unit_price"})
    demand, raw = SERVICE.predict_qty(context, body.unit_price)
    return PredictResponse(predicted_qty=demand, model_output=raw, unit_price=body.unit_price)


@app.post("/optimize-price", response_model=OptimizeResponse)
def optimize(body: OptimizeRequest) -> OptimizeResponse:
    """Sweep prices and keep the revenue maximum, or the profit maximum when cost is set."""
    _require_model()
    context = body.model_dump(exclude={"min_price", "max_price", "step", "unit_cost"})

    def predict_at(price: float) -> float:
        demand, _raw = SERVICE.predict_qty(context, price)
        return demand

    return optimize_price(
        predict_at,
        min_price=body.min_price,
        max_price=body.max_price,
        step=body.step,
        unit_cost=body.unit_cost,
    )


@app.get("/metrics")
def metrics() -> Response:
    """Prometheus text exposition. Counters live in this process only."""
    return Response(
        content=METRICS.render(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
