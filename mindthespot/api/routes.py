"""FastAPI route handlers for MindTheSpot REST API."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from mindthespot.api.auth import UserContext, get_current_user_context
from mindthespot.api.schemas import (
    AnomalyResponse,
    CacheRefreshResponse,
    CacheStatusResponse,
    HealthResponse,
    PivotRecommendationResponse,
    PoolHistoryResponse,
    PoolSummaryResponse,
    WatchlistCreateRequest,
)
from mindthespot.api.service import SpotDataService
from mindthespot.config.models import WatchlistEntry

router = APIRouter(prefix="/api")

# Singleton data service instance
_service_instance: SpotDataService | None = None


def get_spot_service() -> SpotDataService:
    """Dependency injection provider for SpotDataService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = SpotDataService()
    return _service_instance


@router.get("/health", response_model=HealthResponse, tags=["Health"])
def get_health() -> HealthResponse:
    """Service health and liveness check."""
    return HealthResponse(
        status="ok",
        version="0.1.0",
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get("/v1/anomalies", response_model=list[AnomalyResponse], tags=["Anomalies"])
def list_anomalies(
    service: Annotated[SpotDataService, Depends(get_spot_service)],
    severity: Annotated[
        str | None,
        Query(description="Filter by severity: 'CRITICAL', 'ELEVATED', 'STABLE'"),
    ] = None,
    region: Annotated[
        str | None,
        Query(description="Filter by GCP region, e.g. 'europe-west4'"),
    ] = None,
    watchlist_only: Annotated[
        bool,
        Query(description="Restrict anomalies strictly to user watchlist"),
    ] = False,
    price_filter: Annotated[
        str | None,
        Query(description="Filter by price shift: 'HIKE' or 'DROP'"),
    ] = None,
) -> list[AnomalyResponse]:
    """Retrieve active preemption and pricing regime shifts."""
    return service.get_anomalies(
        severity=severity,
        region=region,
        watchlist_only=watchlist_only,
        price_filter=price_filter,
    )


@router.get("/v1/pools", response_model=list[PoolSummaryResponse], tags=["Pools"])
def list_pools(
    service: Annotated[SpotDataService, Depends(get_spot_service)],
    region: Annotated[str | None, Query(description="Filter by region")] = None,
    family: Annotated[str | None, Query(description="Filter by instance family")] = None,
    watchlist_only: Annotated[bool, Query(description="Filter to watchlist")] = False,
    search: Annotated[str | None, Query(description="Search text in pool key or label")] = None,
) -> list[PoolSummaryResponse]:
    """List monitored Spot instance pools across regions and zones."""
    return service.get_all_pools(
        region=region,
        family=family,
        watchlist_only=watchlist_only,
        search=search,
    )


@router.get(
    "/v1/pools/{region}/{zone}/{machine_type}/history",
    response_model=PoolHistoryResponse,
    tags=["Pools"],
)
def get_pool_history(
    region: str,
    zone: str,
    machine_type: str,
    service: Annotated[SpotDataService, Depends(get_spot_service)],
) -> PoolHistoryResponse:
    """Retrieve 30-day preemption points and 1-year pricing intervals for a pool."""
    history = service.get_pool_history(region, zone, machine_type)
    if not history:
        raise HTTPException(
            status_code=404,
            detail=f"Pool not found: {region}/{zone}/{machine_type}",
        )
    return history


@router.get(
    "/v1/pivots/{region}/{zone}/{machine_type}",
    response_model=PivotRecommendationResponse,
    tags=["Pivots"],
)
def get_pool_pivots(
    region: str,
    zone: str,
    machine_type: str,
    service: Annotated[SpotDataService, Depends(get_spot_service)],
) -> PivotRecommendationResponse:
    """Retrieve ranked sibling zone and equivalent family pivot recommendations."""
    pivots = service.get_pivot_recommendations(region, zone, machine_type)
    if not pivots:
        raise HTTPException(
            status_code=404,
            detail=f"Pool not found for pivot lookup: {region}/{zone}/{machine_type}",
        )
    return pivots


@router.get("/v1/watchlist", response_model=list[WatchlistEntry], tags=["Watchlist"])
def get_watchlist(
    service: Annotated[SpotDataService, Depends(get_spot_service)],
) -> list[WatchlistEntry]:
    """Retrieve user-configured watchlist entries."""
    return service.watchlist.watchlist


@router.post("/v1/watchlist", response_model=dict, tags=["Watchlist"])
def add_watchlist_entry(
    req: WatchlistCreateRequest,
    service: Annotated[SpotDataService, Depends(get_spot_service)],
) -> dict:
    """Add custom instance pools to dynamic active watchlist."""
    added_keys = service.add_watchlist_entry(req)
    return {
        "status": "success",
        "message": f"Added {len(added_keys)} pool targets to watchlist",
        "targets": added_keys,
    }


@router.delete(
    "/v1/watchlist/{region}/{zone}/{machine_type}",
    response_model=dict,
    tags=["Watchlist"],
)
def remove_watchlist_entry(
    region: str,
    zone: str,
    machine_type: str,
    service: Annotated[SpotDataService, Depends(get_spot_service)],
) -> dict:
    """Remove a specific instance pool from watchlist."""
    success = service.remove_watchlist_pool(region, zone, machine_type)
    return {
        "status": "success",
        "message": f"Removed {region}/{zone}/{machine_type} from watchlist",
        "success": success,
    }


@router.delete(
    "/v1/watchlist",
    response_model=dict,
    tags=["Watchlist"],
)
def delete_watchlist_target(
    region: str,
    service: Annotated[SpotDataService, Depends(get_spot_service)],
    name: str | None = None,
) -> dict:
    """Remove a whole named or regional watchlist entry and reset associated pools."""
    success = service.remove_watchlist_target(name=name, region=region)
    return {
        "status": "success",
        "message": f"Removed watchlist target {name or region}",
        "success": success,
    }


@router.post(
    "/v1/watchlist/toggle",
    response_model=dict,
    tags=["Watchlist"],
)
def toggle_watchlist_entry(
    req: dict,
    service: Annotated[SpotDataService, Depends(get_spot_service)],
) -> dict:
    """Toggle watchlist status for an individual instance pool."""
    region = req.get("region", "")
    zone = req.get("zone", "")
    machine_type = req.get("machine_type", "")
    is_watchlist = bool(req.get("is_watchlist", True))
    label = req.get("custom_label")
    success = service.toggle_watchlist_pool(region, zone, machine_type, is_watchlist, label)
    return {
        "status": "success",
        "is_watchlist": is_watchlist,
        "pool": f"{region}/{zone}/{machine_type}",
        "success": success,
    }


@router.get("/v1/auth/me", response_model=UserContext, tags=["Authentication"])
def get_authenticated_user(
    user: Annotated[UserContext, Depends(get_current_user_context)],
) -> UserContext:
    """Retrieve the current user's authenticated identity from Cloud IAP."""
    return user


@router.get("/v1/cache/status", response_model=CacheStatusResponse, tags=["Cache"])
def get_cache_status(
    service: Annotated[SpotDataService, Depends(get_spot_service)],
) -> CacheStatusResponse:
    """Retrieve in-memory cache metadata, sync timestamp, and telemetry source."""
    status = service.get_cache_status()
    return CacheStatusResponse(**status)


@router.post("/v1/cache/refresh", response_model=CacheRefreshResponse, tags=["Cache"])
def refresh_cache(
    service: Annotated[SpotDataService, Depends(get_spot_service)],
) -> CacheRefreshResponse:
    """Trigger an asynchronous, non-blocking cache refresh from BigQuery."""
    service.trigger_background_sync()
    return CacheRefreshResponse(
        status="triggered",
        message="Background cache synchronization from BigQuery initiated.",
        triggered_at=datetime.now(UTC).isoformat(),
    )
