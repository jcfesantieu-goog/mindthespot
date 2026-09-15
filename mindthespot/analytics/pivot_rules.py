"""Pivot recommendation matrix and candidate matching rules."""

from pydantic import BaseModel, Field

EQUIVALENT_FAMILIES_MAP: dict[str, list[str]] = {
    "c4d": ["c3d", "c4a", "n2d"],
    "c3d": ["c4d", "c4a", "n2d"],
    "c4a": ["c4d", "c3d", "n2d"],
    "c3": ["c2", "c4d", "c3d", "n4"],
    "c2": ["c3", "c4d", "c3d"],
    "n4": ["c3", "c3d", "n2d", "n2"],
    "n2d": ["n2", "e2", "c3d", "n4"],
    "n2": ["n2d", "e2", "c3", "n4"],
    "t2d": ["t2a", "n2d", "e2"],
    "t2a": ["t2d", "c4a", "n2d"],
    "e2": ["n2d", "n2", "t2d"],
}


class PivotCandidate(BaseModel):
    """A recommended alternative instance pool."""

    pivot_type: str = Field(..., description="'ZONE_PIVOT' or 'FAMILY_PIVOT'")
    region: str
    origin_zone: str
    origin_machine_type: str
    origin_family: str
    origin_7d_rate: float
    origin_hourly_price: float
    pivot_zone: str
    pivot_machine_type: str
    pivot_family: str
    pivot_7d_rate: float
    pivot_hourly_price: float
    preemption_savings: float
    cost_difference: float
    recommendation_reason: str


def find_pivot_candidates_for_pool(
    origin_pool: dict,
    all_pools: list[dict],
    max_candidates: int = 5,
) -> list[PivotCandidate]:
    """Find and rank candidate pivot pools (sibling zones and equivalent families)."""
    candidates: list[PivotCandidate] = []
    region = origin_pool["region"]
    origin_zone = origin_pool["zone"]
    origin_mt = origin_pool["machine_type"]
    origin_family = origin_pool["family"]
    origin_7d = origin_pool.get("recent_7d_rate", 0.0)
    origin_price = origin_pool.get("hourly_price", 0.0)

    for pool in all_pools:
        # Same region only
        if pool["region"] != region:
            continue
        # Candidate must be STABLE with low preemption
        if pool.get("severity") != "STABLE" or pool.get("recent_7d_rate", 1.0) > 0.10:
            continue

        p_zone = pool["zone"]
        p_mt = pool["machine_type"]
        p_family = pool["family"]
        p_7d = pool.get("recent_7d_rate", 0.0)
        p_price = pool.get("hourly_price", 0.0)
        savings = round(origin_7d - p_7d, 4)
        cost_diff = round(origin_price - p_price, 4)

        # 1. Sibling Zone Candidate (same machine type, different zone)
        if p_mt == origin_mt and p_zone != origin_zone:
            candidates.append(
                PivotCandidate(
                    pivot_type="ZONE_PIVOT",
                    region=region,
                    origin_zone=origin_zone,
                    origin_machine_type=origin_mt,
                    origin_family=origin_family,
                    origin_7d_rate=origin_7d,
                    origin_hourly_price=origin_price,
                    pivot_zone=p_zone,
                    pivot_machine_type=p_mt,
                    pivot_family=p_family,
                    pivot_7d_rate=p_7d,
                    pivot_hourly_price=p_price,
                    preemption_savings=savings,
                    cost_difference=cost_diff,
                    recommendation_reason="Sibling zone with stable preemption profile",
                )
            )

        # 2. Equivalent Family Candidate
        allowed_equiv = EQUIVALENT_FAMILIES_MAP.get(origin_family, [])
        if p_family in allowed_equiv and p_family != origin_family:
            candidates.append(
                PivotCandidate(
                    pivot_type="FAMILY_PIVOT",
                    region=region,
                    origin_zone=origin_zone,
                    origin_machine_type=origin_mt,
                    origin_family=origin_family,
                    origin_7d_rate=origin_7d,
                    origin_hourly_price=origin_price,
                    pivot_zone=p_zone,
                    pivot_machine_type=p_mt,
                    pivot_family=p_family,
                    pivot_7d_rate=p_7d,
                    pivot_hourly_price=p_price,
                    preemption_savings=savings,
                    cost_difference=cost_diff,
                    recommendation_reason="Equivalent compute architecture with lower preemption risk",
                )
            )

    # Rank by preemption savings descending, then cost difference descending
    candidates.sort(key=lambda c: (c.preemption_savings, c.cost_difference), reverse=True)
    return candidates[:max_candidates]
