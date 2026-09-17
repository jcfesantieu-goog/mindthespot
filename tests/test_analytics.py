"""Tests for MindTheSpot statistical regime shift detection and pivot rules."""

from mindthespot.analytics.pivot_rules import (
    EQUIVALENT_FAMILIES_MAP,
    find_pivot_candidates_for_pool,
)
from mindthespot.analytics.statistical import (
    classify_preemption_severity,
    compute_preemption_regime_shift,
    detect_price_step_change,
)


def test_compute_regime_shift_on_spike():
    # 23 days baseline of 0.03-0.05, then 7 days spiking to 0.35-0.40
    baseline = [0.04] * 23
    spike_7d = [0.35, 0.38, 0.40, 0.36, 0.39, 0.41, 0.42]
    series = baseline + spike_7d

    metrics = compute_preemption_regime_shift(series)
    assert metrics["severity"] == "CRITICAL"
    assert metrics["z_score"] >= 2.5
    assert metrics["recent_7d_rate"] >= 0.35
    assert metrics["baseline_rate"] == 0.04
    assert metrics["rate_delta"] > 0.30


def test_noise_floor_prevents_false_positives_on_micro_fluctuations():
    # Baseline 0.00, recent 0.01
    baseline = [0.0] * 23
    recent = [0.01] * 7
    series = baseline + recent

    metrics = compute_preemption_regime_shift(series)
    # Even though baseline stddev is 0, noise floor of 0.02 keeps Z = 0.01 / 0.02 = 0.5
    assert metrics["z_score"] == 0.5
    assert metrics["severity"] == "STABLE"


def test_classify_preemption_severity_thresholds():
    # Critical by high Z and rate >= 0.20
    assert (
        classify_preemption_severity(z_score=2.8, recent_7d_rate=0.22, rate_delta=0.18)
        == "CRITICAL"
    )
    # Critical by huge delta >= 0.25
    assert (
        classify_preemption_severity(z_score=1.5, recent_7d_rate=0.26, rate_delta=0.26)
        == "CRITICAL"
    )
    # Critical by absolute rate >= 0.50
    assert (
        classify_preemption_severity(z_score=1.0, recent_7d_rate=0.52, rate_delta=0.05)
        == "CRITICAL"
    )

    # Elevated
    assert (
        classify_preemption_severity(z_score=1.9, recent_7d_rate=0.16, rate_delta=0.10)
        == "ELEVATED"
    )
    assert (
        classify_preemption_severity(z_score=1.2, recent_7d_rate=0.18, rate_delta=0.16)
        == "ELEVATED"
    )

    # Stable
    assert (
        classify_preemption_severity(z_score=0.5, recent_7d_rate=0.05, rate_delta=0.01) == "STABLE"
    )


def test_detect_price_step_change():
    # 10% increase from $0.15 to $0.165
    is_hike, delta = detect_price_step_change(0.165, 0.15)
    assert is_hike is True
    assert delta == 0.10

    # 5% increase: no alert
    is_hike, delta = detect_price_step_change(0.1575, 0.15)
    assert is_hike is False
    assert delta == 0.05

    # None or zero previous price: safe fallback
    is_hike, delta = detect_price_step_change(0.15, None)
    assert is_hike is False
    assert delta == 0.0


def test_equivalent_families_matrix():
    assert "c3d" in EQUIVALENT_FAMILIES_MAP["c4d"]
    assert "c4a" in EQUIVALENT_FAMILIES_MAP["c4d"]
    assert "n2d" in EQUIVALENT_FAMILIES_MAP["c4d"]
    assert "c4d" in EQUIVALENT_FAMILIES_MAP["c3d"]
    assert "c2" in EQUIVALENT_FAMILIES_MAP["c3"]
    assert "c3" in EQUIVALENT_FAMILIES_MAP["n4"]
    assert "t2a" in EQUIVALENT_FAMILIES_MAP["t2d"]
    assert "t2d" in EQUIVALENT_FAMILIES_MAP["t2a"]


def test_find_pivot_candidates_for_congested_pool():
    congested_pool = {
        "region": "europe-west4",
        "zone": "europe-west4-a",
        "machine_type": "c4d-standard-16",
        "family": "c4d",
        "severity": "CRITICAL",
        "recent_7d_rate": 0.42,
        "hourly_price": 0.25,
    }

    all_pools = [
        # Sibling zone candidate (stable, 5% preemption)
        {
            "region": "europe-west4",
            "zone": "europe-west4-b",
            "machine_type": "c4d-standard-16",
            "family": "c4d",
            "severity": "STABLE",
            "recent_7d_rate": 0.05,
            "hourly_price": 0.25,
        },
        # Equivalent family candidate in same zone (C3D in europe-west4-a, stable, 4% preemption, cheaper)
        {
            "region": "europe-west4",
            "zone": "europe-west4-a",
            "machine_type": "c3d-standard-16",
            "family": "c3d",
            "severity": "STABLE",
            "recent_7d_rate": 0.04,
            "hourly_price": 0.22,
        },
        # Equivalent family candidate in sibling zone (C3D in europe-west4-b)
        {
            "region": "europe-west4",
            "zone": "europe-west4-b",
            "machine_type": "c3d-standard-16",
            "family": "c3d",
            "severity": "STABLE",
            "recent_7d_rate": 0.04,
            "hourly_price": 0.22,
        },
        # Another congested pool (should NOT be recommended)
        {
            "region": "europe-west4",
            "zone": "europe-west4-c",
            "machine_type": "c4d-standard-16",
            "family": "c4d",
            "severity": "CRITICAL",
            "recent_7d_rate": 0.38,
            "hourly_price": 0.25,
        },
        # Different region (should NOT be recommended)
        {
            "region": "us-central1",
            "zone": "us-central1-a",
            "machine_type": "c4d-standard-16",
            "family": "c4d",
            "severity": "STABLE",
            "recent_7d_rate": 0.02,
            "hourly_price": 0.23,
        },
    ]

    pivots = find_pivot_candidates_for_pool(congested_pool, all_pools)
    assert len(pivots) == 3

    types = {p.pivot_type for p in pivots}
    assert "SAME_ZONE_PIVOT" in types
    assert "ZONE_PIVOT" in types
    assert "FAMILY_PIVOT" in types

    # First pivot MUST be SAME_ZONE_PIVOT (Priority 1)
    assert pivots[0].pivot_type == "SAME_ZONE_PIVOT"
    assert pivots[0].pivot_zone == "europe-west4-a"
    assert pivots[0].cost_savings_pct > 0.0

    zone_pivot = next(p for p in pivots if p.pivot_type == "ZONE_PIVOT")
    assert zone_pivot.pivot_zone == "europe-west4-b"
    assert zone_pivot.preemption_savings == 0.37

    same_zone_pivot = next(p for p in pivots if p.pivot_type == "SAME_ZONE_PIVOT")
    assert same_zone_pivot.pivot_family == "c3d"
    assert same_zone_pivot.preemption_savings == 0.38
    assert same_zone_pivot.cost_difference == 0.03
