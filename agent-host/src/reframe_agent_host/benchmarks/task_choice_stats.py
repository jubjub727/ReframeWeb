from __future__ import annotations


def latency_summary(latencies: list[float]) -> dict[str, float | None]:
    if not latencies:
        return {
            "average": None,
            "best": None,
            "worst": None,
            "p50": None,
        }

    sorted_latencies = sorted(latencies)
    return {
        "average": sum(latencies) / len(latencies),
        "best": sorted_latencies[0],
        "worst": sorted_latencies[-1],
        "p50": percentile(sorted_latencies, 0.5),
    }


def percentile(sorted_values: list[float], fraction: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]

    position = fraction * (len(sorted_values) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    upper_weight = position - lower_index
    lower_weight = 1.0 - upper_weight
    return (
        sorted_values[lower_index] * lower_weight
        + sorted_values[upper_index] * upper_weight
    )
