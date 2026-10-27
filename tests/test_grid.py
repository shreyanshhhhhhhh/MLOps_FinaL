"""The committed grid is the experiment, so it has to stay large enough."""

from __future__ import annotations

from types import SimpleNamespace

from src.config import load_params
from src.select_best import choose_best_run
from src.train import iter_model_configs

REQUIRED_FAMILIES = {
    "linear_regression",
    "ridge",
    "random_forest",
    "gradient_boosting",
    "lightgbm",
}


def test_grid_has_at_least_twelve_runs_across_four_families() -> None:
    configs = iter_model_configs(load_params()["models"])
    families = {family for family, _params in configs}
    assert len(configs) >= 12
    assert REQUIRED_FAMILIES <= families


def _run(run_id: str, rmse: float, started: int) -> SimpleNamespace:
    return SimpleNamespace(
        info=SimpleNamespace(run_id=run_id, start_time=started),
        data=SimpleNamespace(metrics={"test_rmse": rmse}),
    )


def test_choose_best_prefers_lower_rmse_then_newer_run() -> None:
    older = _run("aaa", 1.0, 10)
    newer = _run("bbb", 1.0, 20)
    worse = _run("ccc", 2.0, 30)
    assert choose_best_run([older, worse, newer]).info.run_id == "bbb"
