"""Pivot recommendation matrix and candidate matching rules."""

import re
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


def extract_core_size(machine_type: str) -> int:
    """Extract the core/vCPU count suffix from a machine type string (e.g. c4d-standard-8 -> 8)."""
    m = re.search(r"-(\d+)$", machine_type.strip())
    return int(m.group(1)) if m else 0


class PivotCandidate(BaseModel):
    """A recommended alternative instance pool."""

    pivot_type: str = Field(..., description="'SAME_ZONE_PIVOT', 'ZONE_PIVOT', or 'FAMILY_PIVOT'")
    priority_rank: int = Field(default=2, description="1=Same Zone Same Size, 2=Sibling Zone Same MT, 3=Sibling Zone Same Size")
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
    cost_savings_pct: float = Field(default=0.0, description="Cost savings percentage relative to origin pool")
    recommendation_reason: str


def find_pivot_candidates_for_pool(
    origin_pool: dict,
    all_pools: list[dict],
    max_candidates: int = 5,
) -> list[PivotCandidate]:
    """Find and rank candidate pivot pools prioritizing same-zone same-size, then same region."""
    candidates: list[PivotCandidate] = []
    region = origin_pool["region"]
    origin_zone = origin_pool["zone"]
    origin_mt = origin_pool["machine_type"]
    origin_family = origin_pool["family"]
    origin_cores = extract_core_size(origin_mt)
    origin_7d = origin_pool.get("recent_7d_rate", 0.0)
    origin_price = origin_pool.get("hourly_price", 0.0)
    allowed_equiv = EQUIVALENT_FAMILIES_MAP.get(origin_family, [])

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
        p_cores = extract_core_size(p_mt)
        p_7d = pool.get("recent_7d_rate", 0.0)
        p_price = pool.get("hourly_price", 0.0)
        savings = round(origin_7d - p_7d, 4)
        cost_diff = round(origin_price - p_price, 4)
        savings_pct = (
            round(((origin_price - p_price) / origin_price) * 100.0, 1)
            if origin_price > 0
            else 0.0
        )

        # 1. Priority 1: Same Zone, Same Core Size, Equivalent Family (zero disk migration!)
        if p_zone == origin_zone and p_family in allowed_equiv and p_cores == origin_cores and origin_cores > 0:
            candidates.append(
                PivotCandidate(
                    pivot_type="SAME_ZONE_PIVOT",
                    priority_rank=1,
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
                    cost_savings_pct=savings_pct,
                    recommendation_reason="Same-zone fallback with equivalent core size (zero disk migration or cross-zone egress)",
                )
            )

        # 2. Priority 2: Sibling Zone Candidate (same machine type, different zone)
        elif p_mt == origin_mt and p_zone != origin_zone:
            candidates.append(
                PivotCandidate(
                    pivot_type="ZONE_PIVOT",
                    priority_rank=2,
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
                    cost_savings_pct=savings_pct,
                    recommendation_reason="Sibling zone with stable preemption profile and identical instance family",
                )
            )

        # 3. Priority 3: Sibling Zone Candidate (same core size, equivalent family, different zone)
        elif p_zone != origin_zone and p_family in allowed_equiv and p_cores == origin_cores and origin_cores > 0:
            candidates.append(
                PivotCandidate(
                    pivot_type="FAMILY_PIVOT",
                    priority_rank=3,
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
                    cost_savings_pct=savings_pct,
                    recommendation_reason="Equivalent compute architecture in sibling zone with lower preemption risk",
                )
            )

    # Rank by: 1) priority_rank ASC (same-zone first), 2) preemption_savings DESC, 3) cost_difference DESC
    candidates.sort(key=lambda c: (c.priority_rank, -c.preemption_savings, -c.cost_difference))
    return candidates[:max_candidates]
