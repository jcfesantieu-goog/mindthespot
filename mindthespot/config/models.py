"""Configuration models for MindTheSpot catalog and watchlists."""

from pydantic import BaseModel, Field, field_validator


class MachineFamilyConfig(BaseModel):
    """Configuration for a specific machine family."""

    family: str = Field(..., description="Family prefix, e.g. 'c4d', 'c3d', 'c4a', 'n2d'")
    category: str = Field(
        default="general-purpose",
        description="Category: 'compute-optimized', 'general-purpose', 'accelerator', etc.",
    )
    description: str | None = None
    machine_types: list[str] = Field(
        ...,
        min_length=1,
        description="List of concrete machine types, e.g. ['c4d-standard-8', 'c4d-standard-16']",
    )
    equivalent_families: list[str] = Field(
        default_factory=list,
        description="List of alternative interchangeable family identifiers for pivots",
    )

    @field_validator("family")
    @classmethod
    def normalize_family(cls, v: str) -> str:
        return v.strip().lower()


class RegionConfig(BaseModel):
    """Configuration for a monitored GCP region and its zones."""

    region: str = Field(..., description="GCP region identifier, e.g. 'europe-west4'")
    zones: list[str] = Field(
        ...,
        min_length=1,
        description="List of zones, e.g. ['europe-west4-a', 'europe-west4-b', 'europe-west4-c']",
    )
    description: str | None = None

    @field_validator("region")
    @classmethod
    def normalize_region(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("zones")
    @classmethod
    def validate_and_normalize_zones(cls, v: list[str], info) -> list[str]:
        cleaned = [z.strip().lower() for z in v]
        region = info.data.get("region")
        if region:
            for zone in cleaned:
                if not zone.startswith(region):
                    raise ValueError(f"Zone '{zone}' must start with region '{region}'")
        return cleaned


class CatalogConfig(BaseModel):
    """Default global curated catalog definition."""

    version: str = Field(default="1.0")
    regions: list[RegionConfig] = Field(..., min_length=1)
    families: list[MachineFamilyConfig] = Field(..., min_length=1)

    def get_family(self, family_name: str) -> MachineFamilyConfig | None:
        name = family_name.lower().strip()
        for f in self.families:
            if f.family == name:
                return f
        return None

    def get_region(self, region_name: str) -> RegionConfig | None:
        name = region_name.lower().strip()
        for r in self.regions:
            if r.region == name:
                return r
        return None


class WatchlistEntry(BaseModel):
    """Custom team watchlist entry for specific high-priority workloads."""

    name: str | None = Field(default=None, description="Human-readable label or team identifier")
    region: str = Field(..., description="Target GCP region")
    zones: list[str] = Field(
        default_factory=list,
        description="Target zones. If empty, expands to all known zones in the region.",
    )
    machine_types: list[str] = Field(
        ...,
        min_length=1,
        description="Specific machine types to track, e.g. ['c4d-standard-16']",
    )
    alert_threshold_z: float | None = Field(
        default=None,
        description="Optional custom Z-score alert threshold override (defaults to 2.5)",
    )
    alert_threshold_delta: float | None = Field(
        default=None,
        description="Optional custom preemption rate spike delta override (defaults to 0.20)",
    )


class WatchlistConfig(BaseModel):
    """User-defined custom watchlist configuration."""

    version: str = Field(default="1.0")
    watchlist: list[WatchlistEntry] = Field(default_factory=list)


class InstancePoolTarget(BaseModel):
    """A fully resolved target pool for crawling, analysis, and pivot matching."""

    region: str
    zone: str
    machine_type: str
    family: str
    is_watchlist: bool = False
    custom_label: str | None = None

    @property
    def pool_key(self) -> str:
        """Unique key identifying this regional-zonal-machine pool."""
        return f"{self.region}/{self.zone}/{self.machine_type}"
