"""Statistical anomaly detection engine for Spot VM preemption and pricing."""

import math
from typing import Any


def calculate_mean(values: list[float]) -> float:
    """Calculate arithmetic mean of a list of floats."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def calculate_sample_stddev(values: list[float], mean: float | None = None) -> float:
    """Calculate sample standard deviation (N-1 degrees of freedom)."""
    if len(values) < 2:
        return 0.0
    avg = mean if mean is not None else calculate_mean(values)
    variance = sum((x - avg) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def compute_preemption_regime_shift(
    daily_rates: list[float],
    min_noise_floor_stddev: float = 0.02,
) -> dict[str, Any]:
    """Compute 7-day recent vs 23-day baseline statistical regime shift metrics.

    Parameters:
        daily_rates: Chronological list of daily preemption rates (0.0 to 1.0).
        min_noise_floor_stddev: Minimum standard deviation floor to avoid false positives
            when baseline preemption rate has near-zero variance.
    """
    if not daily_rates:
        return {
            "latest_rate": 0.0,
            "recent_7d_rate": 0.0,
            "baseline_rate": 0.0,
            "rate_delta": 0.0,
            "z_score": 0.0,
            "severity": "STABLE",
        }

    latest_rate = daily_rates[-1]

    # Split into recent 7 days and prior baseline
    if len(daily_rates) <= 7:
        recent_window = daily_rates
        baseline_window = daily_rates
    else:
        recent_window = daily_rates[-7:]
        baseline_window = daily_rates[:-7]

    recent_7d_rate = calculate_mean(recent_window)
    baseline_rate = calculate_mean(baseline_window)
    baseline_stddev = calculate_sample_stddev(baseline_window, baseline_rate)

    effective_stddev = max(baseline_stddev, min_noise_floor_stddev)
    rate_delta = recent_7d_rate - baseline_rate
    z_score = rate_delta / effective_stddev

    # Classify severity
    severity = classify_preemption_severity(z_score, recent_7d_rate, rate_delta)

    return {
        "latest_rate": round(latest_rate, 4),
        "recent_7d_rate": round(recent_7d_rate, 4),
        "baseline_rate": round(baseline_rate, 4),
        "rate_delta": round(rate_delta, 4),
        "z_score": round(z_score, 2),
        "severity": severity,
    }


def classify_preemption_severity(
    z_score: float,
    recent_7d_rate: float,
    rate_delta: float,
) -> str:
    """Classify anomaly severity based on statistical Z-score and absolute rate thresholds.

    CRITICAL:
        (Z >= 2.5 and recent_7d_rate >= 0.20) OR rate_delta >= 0.25 OR recent_7d_rate >= 0.50
    ELEVATED:
        (Z >= 1.8 and recent_7d_rate >= 0.15) OR rate_delta >= 0.15
    STABLE:
        All other conditions
    """
    if (
        (z_score >= 2.5 and recent_7d_rate >= 0.20)
        or (rate_delta >= 0.25)
        or (recent_7d_rate >= 0.50)
    ):
        return "CRITICAL"
    elif (z_score >= 1.8 and recent_7d_rate >= 0.15) or (rate_delta >= 0.15):
        return "ELEVATED"
    return "STABLE"


def detect_price_step_change(
    current_price: float,
    previous_price: float | None,
    hike_threshold_pct: float = 0.10,
) -> tuple[bool, float]:
    """Detect discrete spot price changes exceeding a percentage threshold (e.g. +10%)."""
    if previous_price is None or previous_price <= 0.0:
        return False, 0.0

    pct_change = (current_price - previous_price) / previous_price
    is_hike = pct_change >= hike_threshold_pct
    return is_hike, round(pct_change, 4)
