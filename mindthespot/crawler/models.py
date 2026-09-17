"""Data models for GCP Capacity History API responses and crawler outputs."""

from datetime import datetime

from pydantic import BaseModel, Field


class DailyPreemptionRate(BaseModel):
    """Daily spot preemption rate data point."""

    date: str = Field(..., description="Date of telemetry YYYY-MM-DD")
    preemption_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Daily preemption probability rate (0.0 to 1.0)",
    )


class PreemptionSnapshotRecord(BaseModel):
    """Sanitized and processed 30-day preemption history for a specific zone & machine type."""

    snapshot_date: str = Field(..., description="Date of crawl snapshot YYYY-MM-DD")
    crawled_at: str = Field(..., description="ISO 8601 timestamp of crawl execution")
    region: str
    zone: str
    machine_type: str
    family: str
    rates: list[DailyPreemptionRate] = Field(default_factory=list)
    latest_rate: float = 0.0
    avg_7d_rate: float = 0.0
    avg_30d_rate: float = 0.0
    is_watchlist: bool = False
    custom_label: str | None = None


class PriceIntervalRecord(BaseModel):
    """Historical spot pricing interval."""

    start_time: str = Field(..., description="ISO 8601 start timestamp")
    end_time: str | None = Field(
        default=None, description="ISO 8601 end timestamp or None if active"
    )
    hourly_price: float = Field(..., ge=0.0, description="Price in currency units per hour")
    currency: str = Field(default="USD")


class PriceSnapshotRecord(BaseModel):
    """Sanitized 1-year historical pricing for a specific region & machine type."""

    snapshot_date: str = Field(..., description="Date of crawl snapshot YYYY-MM-DD")
    crawled_at: str = Field(..., description="ISO 8601 timestamp of crawl execution")
    region: str
    machine_type: str
    family: str
    intervals: list[PriceIntervalRecord] = Field(default_factory=list)
    current_hourly_price: float = 0.0
    currency: str = Field(default="USD")


class CrawlSummary(BaseModel):
    """Summary metrics of a crawl execution."""

    snapshot_date: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    total_preemption_pools: int
    total_price_pools: int
    successful_preemption_queries: int
    successful_price_queries: int
    failed_queries: int
    anomalies_detected: int = 0
