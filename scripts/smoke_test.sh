#!/bin/sh
# Curl a running PriceOptima container. Exit non-zero on any failed check.
# Usage: scripts/smoke_test.sh
#        BASE_URL=http://127.0.0.1:8000 scripts/smoke_test.sh
set -eu

BASE="${BASE_URL:-http://127.0.0.1:${PORT:-8000}}"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

code="$(curl -sS -o /tmp/priceoptima-health.json -w '%{http_code}' "$BASE/health")" || fail "health request failed"
[ "$code" = "200" ] || fail "health status $code"

code="000"
i=0
while [ "$i" -lt 30 ]; do
    code="$(curl -sS -o /tmp/priceoptima-ready.json -w '%{http_code}' "$BASE/ready" || true)"
    if [ "$code" = "200" ]; then
        break
    fi
    i=$((i + 1))
    sleep 2
done
[ "$code" = "200" ] || fail "ready status $code $(cat /tmp/priceoptima-ready.json 2>/dev/null || true)"

curl -fsS "$BASE/model-info" -o /tmp/priceoptima-model-info.json || fail "model-info request failed"
curl -fsS "$BASE/metrics" -o /tmp/priceoptima-metrics.txt || fail "metrics request failed"

python3 - "$BASE" <<'PY'
import json
import sys
import urllib.request

base = sys.argv[1]
context = {
    "product_category_name": "bed_bath_table",
    "freight_price": 10.25631579,
    "product_weight_g": 350,
    "product_score": 4.0,
    "weekday": 23,
    "weekend": 8,
    "holiday": 3,
    "month": 5,
    "year": 2018,
    "volume": 3800,
    "s": 10.26739356,
    "comp_1": 83.64961538,
    "comp_2": 39.99,
    "comp_3": 39.99,
    "ps1": 3.9,
    "ps2": 4.0,
    "ps3": 4.0,
    "fp1": 16.78038462,
    "fp2": 10.25631579,
    "fp3": 10.25631579,
    "lag_price": 39.99,
    "product_name_lenght": 39,
    "product_description_lenght": 161,
    "product_photos_qty": 2,
}


def post(path, payload):
    request = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


info = json.load(open("/tmp/priceoptima-model-info.json", encoding="utf-8"))
if not info.get("model_name"):
    raise SystemExit("model-info has no model_name")
if not info.get("load_time"):
    raise SystemExit("model-info has no load_time")

predicted = post("/predict-demand", context | {"unit_price": 39.99})
qty = predicted["predicted_qty"]
if not isinstance(qty, (int, float)) or qty != qty:
    raise SystemExit(f"predicted qty is not finite: {qty}")

optimized = post(
    "/optimize-price",
    context | {"min_price": 20, "max_price": 80, "step": 5, "unit_cost": 15},
)
best = optimized["best_price"]
if not 20 <= best <= 80:
    raise SystemExit(f"best price {best} is outside 20..80")
if not optimized["curve"]:
    raise SystemExit("curve is empty")
print(
    "ok",
    info["model_name"],
    "qty",
    round(qty, 4),
    "best_price",
    best,
    "revenue",
    round(optimized["expected_revenue"], 4),
)
PY

grep -q "priceoptima_requests_total" /tmp/priceoptima-metrics.txt || fail "metrics missing request counter"
printf 'smoke test passed against %s\n' "$BASE"
