"""In-process Prometheus text metrics. No client library, so the image stays smaller."""

from __future__ import annotations

import threading
from collections import Counter

# Fixed buckets, in seconds. +Inf is stored as the last counter.
BUCKETS_SECONDS: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)


class MetricsRegistry:
    """Thread-safe counters for request volume, latency, and model evaluations."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: Counter[tuple[str, str]] = Counter()
        self._predictions = 0
        self._latency_sum = 0.0
        self._latency_count = 0
        self._bucket_counts = [0 for _ in range(len(BUCKETS_SECONDS) + 1)]

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()
            self._predictions = 0
            self._latency_sum = 0.0
            self._latency_count = 0
            self._bucket_counts = [0 for _ in range(len(BUCKETS_SECONDS) + 1)]

    def observe_request(self, endpoint: str, status: int, latency_seconds: float) -> None:
        with self._lock:
            self._requests[(endpoint, str(status))] += 1
            self._latency_sum += latency_seconds
            self._latency_count += 1
            placed = False
            for index, upper in enumerate(BUCKETS_SECONDS):
                if latency_seconds <= upper:
                    self._bucket_counts[index] += 1
                    placed = True
                    break
            if not placed:
                self._bucket_counts[-1] += 1

    def increment_predictions(self, count: int = 1) -> None:
        with self._lock:
            self._predictions += count

    def render(self) -> str:
        """Prometheus exposition format, version 0.0.4."""
        with self._lock:
            requests = list(self._requests.items())
            predictions = self._predictions
            latency_sum = self._latency_sum
            latency_count = self._latency_count
            bucket_counts = list(self._bucket_counts)

        lines = [
            "# HELP priceoptima_requests_total HTTP requests by endpoint and status.",
            "# TYPE priceoptima_requests_total counter",
        ]
        for (endpoint, status), count in sorted(requests):
            lines.append(
                f'priceoptima_requests_total{{endpoint="{endpoint}",status="{status}"}} {count}'
            )
        lines.extend(
            [
                "# HELP priceoptima_predictions_total Demand-model evaluations.",
                "# TYPE priceoptima_predictions_total counter",
                f"priceoptima_predictions_total {predictions}",
                "# HELP priceoptima_request_latency_seconds End-to-end request latency.",
                "# TYPE priceoptima_request_latency_seconds histogram",
            ]
        )
        cumulative = 0
        for upper, count in zip(BUCKETS_SECONDS, bucket_counts, strict=False):
            cumulative += count
            lines.append(f'priceoptima_request_latency_seconds_bucket{{le="{upper}"}} {cumulative}')
        cumulative += bucket_counts[-1]
        lines.append(f'priceoptima_request_latency_seconds_bucket{{le="+Inf"}} {cumulative}')
        lines.append(f"priceoptima_request_latency_seconds_sum {latency_sum}")
        lines.append(f"priceoptima_request_latency_seconds_count {latency_count}")
        return "\n".join(lines) + "\n"


METRICS = MetricsRegistry()
