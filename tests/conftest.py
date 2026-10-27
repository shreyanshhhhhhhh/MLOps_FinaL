"""Shared panel fixture. Dates cross a year boundary so a string sort fails."""

from __future__ import annotations

import pandas as pd
import pytest

RAW_COLUMNS = [
    "product_id",
    "product_category_name",
    "month_year",
    "qty",
    "total_price",
    "freight_price",
    "unit_price",
    "product_name_lenght",
    "product_description_lenght",
    "product_photos_qty",
    "product_weight_g",
    "product_score",
    "customers",
    "weekday",
    "weekend",
    "holiday",
    "month",
    "year",
    "s",
    "volume",
    "comp_1",
    "ps1",
    "fp1",
    "comp_2",
    "ps2",
    "fp2",
    "comp_3",
    "ps3",
    "fp3",
    "lag_price",
]

# Not zero-padded in a way that survives a lexical sort across the new year:
# "01-01-2018" < "01-12-2017" as text, but January 2018 is later.
MONTHS = ["01-11-2017", "01-12-2017", "01-01-2018", "01-02-2018", "01-03-2018"]


def make_panel() -> pd.DataFrame:
    """Five months, two products, every raw column populated."""
    rows: list[dict] = []
    for index, month in enumerate(MONTHS):
        for product, category, price in (
            ("bed1", "bed_bath_table", 40.0),
            ("watch1", "watches_gifts", 80.0),
        ):
            qty = 10 + index
            rows.append(
                {
                    "product_id": product,
                    "product_category_name": category,
                    "month_year": month,
                    "qty": qty,
                    "total_price": qty * price,
                    "freight_price": 12.0,
                    "unit_price": price,
                    "product_name_lenght": 30,
                    "product_description_lenght": 120,
                    "product_photos_qty": 2,
                    "product_weight_g": 350,
                    "product_score": 4.2,
                    "customers": 20 + index,
                    "weekday": 22,
                    "weekend": 8,
                    "holiday": 1,
                    "month": int(month[3:5]),
                    "year": int(month[6:10]),
                    "s": 10.0 + index,
                    "volume": 3800,
                    "comp_1": price + 5,
                    "ps1": 4.0,
                    "fp1": 11.0,
                    "comp_2": price,
                    "ps2": 4.1,
                    "fp2": 10.0,
                    "comp_3": price - 2,
                    "ps3": 3.9,
                    "fp3": 9.0,
                    "lag_price": price - 1,
                }
            )
    return pd.DataFrame(rows, columns=RAW_COLUMNS)


@pytest.fixture
def panel() -> pd.DataFrame:
    return make_panel()
