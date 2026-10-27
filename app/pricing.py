"""Search a price grid for the revenue (or profit) maximum and estimate elasticity."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from app.schemas import CurvePoint, OptimizeResponse


def price_grid(min_price: float, max_price: float, step: float) -> list[float]:
    """Inclusive grid. The upper bound is appended when the step does not land on it."""
    prices: list[float] = []
    value = float(min_price)
    while value <= max_price + step * 1e-9:
        prices.append(round(value, 6))
        next_value = value + step
        if next_value <= value:
            break
        value = next_value
    if prices and prices[-1] < max_price - 1e-6:
        prices.append(round(float(max_price), 6))
    return prices


def arc_elasticity(price_a: float, qty_a: float, price_b: float, qty_b: float) -> float | None:
    """Midpoint (arc) elasticity between two prices. Negative means demand falls as price rises."""
    price_avg = (price_a + price_b) / 2.0
    qty_avg = (qty_a + qty_b) / 2.0
    if price_avg == 0 or qty_avg == 0 or price_a == price_b:
        return None
    return ((qty_b - qty_a) / qty_avg) / ((price_b - price_a) / price_avg)


def log_log_slope(prices: list[float], quantities: list[float]) -> float | None:
    """OLS slope of log(qty) on log(price). That slope is a constant elasticity."""
    log_price: list[float] = []
    log_qty: list[float] = []
    for price, qty in zip(prices, quantities, strict=True):
        if price > 0 and qty > 0:
            log_price.append(float(np.log(price)))
            log_qty.append(float(np.log(qty)))
    if len(log_price) < 2:
        return None
    x = np.asarray(log_price, dtype=float)
    y = np.asarray(log_qty, dtype=float)
    centered = x - x.mean()
    variance = float(np.dot(centered, centered))
    if variance == 0:
        return None
    return float(np.dot(centered, y - y.mean()) / variance)


def _local_arc(prices: list[float], quantities: list[float], index: int) -> float | None:
    if len(prices) < 2:
        return None
    if index <= 0:
        left, right = 0, 1
    elif index >= len(prices) - 1:
        left, right = len(prices) - 2, len(prices) - 1
    else:
        left, right = index - 1, index + 1
    return arc_elasticity(prices[left], quantities[left], prices[right], quantities[right])


def optimize_price(
    predict_qty: Callable[[float], float],
    *,
    min_price: float,
    max_price: float,
    step: float,
    unit_cost: float | None,
) -> OptimizeResponse:
    """Score every price and keep the one with the highest revenue, or profit when cost is given.

    Predicted demand is floored at zero. A negative quantity is not a sellable
    outcome, and it would make revenue point the wrong way.
    """
    prices = price_grid(min_price, max_price, step)
    curve: list[CurvePoint] = []
    scored: list[tuple[float, CurvePoint]] = []
    for price in prices:
        demand = max(float(predict_qty(price)), 0.0)
        revenue = price * demand
        profit = None if unit_cost is None else (price - unit_cost) * demand
        point = CurvePoint(
            price=price,
            predicted_qty=demand,
            revenue=revenue,
            profit=profit,
        )
        curve.append(point)
        objective_value = revenue if profit is None else profit
        scored.append((objective_value, point))
    best = max(scored, key=lambda item: (item[0], -item[1].price))[1]
    best_index = next(index for index, point in enumerate(curve) if point.price == best.price)
    quantities = [point.predicted_qty for point in curve]
    window_from = max(0, best_index - 2)
    window_to = min(len(prices), best_index + 3)
    return OptimizeResponse(
        best_price=best.price,
        expected_demand=best.predicted_qty,
        expected_revenue=best.revenue,
        expected_profit=best.profit,
        objective="profit" if unit_cost is not None else "revenue",
        elasticity=_local_arc(prices, quantities, best_index),
        elasticity_method="arc",
        log_log_slope=log_log_slope(
            prices[window_from:window_to], quantities[window_from:window_to]
        ),
        curve=curve,
    )
