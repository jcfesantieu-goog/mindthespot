"""Pydantic request and response schemas for MindTheSpot REST API."""

from pydantic import BaseModel, Field

from mindthespot.analytics.pivot_rules import PivotCandidate
from mindthespot.config.models import WatchlistEntry
from mindthespot.crawler.models import DailyPreemptionRate, PriceIntervalRecord


class HealthResponse(BaseModel):
    """API health status."""

    status: str = "ok"
    version: str = "0.1.0"
    timestamp: str


class AnomalyResponse(BaseModel):
    """Regime shift anomaly item."""

    pool_key: str
    region: str
    zone: str
    machine_type: str
    family: str
    is_watchlist: bool = False
    custom_label: str | None = None
    latest_rate: float
    recent_7d_rate: float
    baseline_rate: float
    rate_delta: float
    z_score: float
    hourly_price: float
    ondemand_hourly_price: float | None = None
    spot_discount_pct: float | None = None
    severity: str  # CRITICAL, ELEVATED, STABLE
    price_hike_detected: bool = False
    price_drop_detected: bool = False
    price_hike_pct: float | None = 0.0
    price_change_pct: float | None = 0.0
    pivot_count: int = 0


class PoolSummaryResponse(BaseModel):
    """Summary record for a single instance pool."""

    pool_key: str
    region: str
    zone: str
    machine_type: str
    family: str
    is_watchlist: bool = False
    custom_label: str | None = None
    latest_rate: float
    avg_7d_rate: float
    avg_30d_rate: float
    hourly_price: float
    ondemand_hourly_price: float | None = None
    spot_discount_pct: float | None = None
    severity: str
    price_hike_detected: bool = False
    price_drop_detected: bool = False
    price_change_pct: float | None = 0.0


class PoolHistoryResponse(BaseModel):
    """Detailed 30-day preemption and 1-year price history for an instance pool."""

    pool_key: str
    region: str
    zone: str
    machine_type: str
    family: str
    is_watchlist: bool = False
    custom_label: str | None = None
    rates: list[DailyPreemptionRate]
    intervals: list[PriceIntervalRecord]
    latest_rate: float
    recent_7d_rate: float
    baseline_rate: float
    rate_delta: float
    z_score: float
    severity: str
    current_hourly_price: float
    ondemand_hourly_price: float | None = None
    spot_discount_pct: float | None = None


class PivotRecommendationResponse(BaseModel):
    """Pivot recommendations for a specific pool."""

    pool_key: str
    origin_severity: str
    pivots: list[PivotCandidate] = Field(default_factory=list)


class WatchlistCreateRequest(BaseModel):
    """Payload to add a custom watchlist pool."""

    name: str | None = Field(default=None, description="Team or workload label")
    region: str
    zones: list[str] = Field(default_factory=list)
    machine_types: list[str] = Field(..., min_length=1)
    alert_threshold_z: float | None = None
    alert_threshold_delta: float | None = None


class WatchlistSyncRequest(BaseModel):
    """Payload to synchronize client-side watchlist state with backend/BigQuery."""

    entries: list[WatchlistEntry] = Field(default_factory=list)
    starred_pools: list[str] = Field(default_factory=list)
    custom_labels: dict[str, str] = Field(default_factory=dict)


class WatchlistSyncResponse(BaseModel):
    """Response containing consolidated server-side and BigQuery watchlist state."""

    status: str = "success"
    entries: list[WatchlistEntry] = Field(default_factory=list)
    starred_pools: list[str] = Field(default_factory=list)
    custom_labels: dict[str, str] = Field(default_factory=dict)


class CacheStatusResponse(BaseModel):
    """Status and telemetry source of the in-memory cache."""

    source: str  # "bigquery" or "synthetic"
    last_synced_at: str | None = None
    total_pools_cached: int
    total_price_intervals: int
    total_preemption_points: int
    is_warming: bool = False


class CacheRefreshResponse(BaseModel):
    """Response from asynchronous cache refresh trigger."""

    status: str
    message: str
    triggered_at: str
