"""Service layer providing Spot telemetry, statistical metrics, and pivot calculations."""

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from mindthespot.analytics.pivot_rules import (
    find_pivot_candidates_for_pool,
)
from mindthespot.analytics.statistical import (
    compute_preemption_regime_shift,
    detect_price_step_change,
)
from mindthespot.api.cache import get_cached, set_cached
from mindthespot.api.schemas import (
    AnomalyResponse,
    PivotRecommendationResponse,
    PoolHistoryResponse,
    PoolSummaryResponse,
    WatchlistCreateRequest,
)
from mindthespot.config.loader import load_catalog, load_watchlist, resolve_targets
from mindthespot.config.models import (
    CatalogConfig,
    InstancePoolTarget,
    WatchlistConfig,
    WatchlistEntry,
)
from mindthespot.crawler.models import DailyPreemptionRate, PriceIntervalRecord


class SpotDataService:
    """Provides analytical spot data, regime shift metrics, and pivot fallbacks."""

    def __init__(
        self,
        catalog: CatalogConfig | None = None,
        watchlist: WatchlistConfig | None = None,
    ) -> None:
        self.catalog = catalog or load_catalog()
        self.watchlist = watchlist or load_watchlist()
        self._custom_watchlist_entries: list[WatchlistEntry] = []
        self._synthetic_pool_cache: dict[str, dict[str, Any]] = {}
        self._initialize_synthetic_dataset()

    def _initialize_synthetic_dataset(self) -> None:
        """Seed realistic 30-day preemption and price histories for catalog pools."""
        targets = resolve_targets(self.catalog, self.watchlist)
        base_date = datetime.now(UTC) - timedelta(days=30)

        # Baseline pricing per machine family
        family_prices = {
            "c4d": 0.038,  # per core approx
            "c3d": 0.035,
            "c4a": 0.030,
            "c3": 0.042,
            "c2": 0.039,
            "n4": 0.034,
            "n2d": 0.032,
            "n2": 0.036,
            "t2d": 0.028,
            "t2a": 0.024,
            "e2": 0.025,
        }

        # Deterministic seed for consistent local telemetry
        rng = random.Random(42)

        for target in targets:
            key = target.pool_key
            family = target.family

            # Derive core count from machine type string
            try:
                cores = int(target.machine_type.split("-")[-1])
            except ValueError:
                cores = 4

            unit_price = family_prices.get(family, 0.035)
            hourly_price = round(unit_price * cores, 4)

            # Build 30-day preemption points
            # Inject realistic regime shift scenarios:
            # 1. europe-west4 / zone-a / c4d is CRITICAL (spikes from 0.04 to 0.42)
            # 2. europe-west9 / zone-a / c3d is ELEVATED (spikes from 0.05 to 0.22)
            # 3. all other pools have stable low preemption (0.02 - 0.06)
            is_critical = (
                target.region == "europe-west4"
                and target.zone == "europe-west4-a"
                and target.family == "c4d"
            )
            is_elevated = (
                target.region == "europe-west9"
                and target.zone == "europe-west9-a"
                and target.family == "c3d"
            )

            rates: list[DailyPreemptionRate] = []
            for d in range(30):
                current_d = base_date + timedelta(days=d)
                d_str = current_d.strftime("%Y-%m-%d")

                if d < 23:
                    # Baseline window
                    r_val = round(rng.uniform(0.02, 0.06), 4)
                else:
                    # Recent 7-day window
                    if is_critical:
                        r_val = round(rng.uniform(0.35, 0.45), 4)
                    elif is_elevated:
                        r_val = round(rng.uniform(0.18, 0.26), 4)
                    else:
                        r_val = round(rng.uniform(0.02, 0.07), 4)

                rates.append(DailyPreemptionRate(date=d_str, preemption_rate=r_val))

            rate_values = [r.preemption_rate for r in rates]
            metrics = compute_preemption_regime_shift(rate_values)

            # Price intervals (1-year history)
            # Inject a +12% price hike for c4d in europe-west4
            has_price_hike = target.region == "europe-west4" and target.family == "c4d"
            prev_price = round(hourly_price * 0.88, 4) if has_price_hike else hourly_price
            intervals = [
                PriceIntervalRecord(
                    start_time=(base_date - timedelta(days=335)).isoformat(),
                    end_time=base_date.isoformat() if has_price_hike else None,
                    hourly_price=prev_price,
                    currency="USD",
                )
            ]
            if has_price_hike:
                intervals.append(
                    PriceIntervalRecord(
                        start_time=base_date.isoformat(),
                        end_time=None,
                        hourly_price=hourly_price,
                        currency="USD",
                    )
                )

            is_hike, hike_pct = detect_price_step_change(
                hourly_price, prev_price if has_price_hike else None
            )

            self._synthetic_pool_cache[key] = {
                "target": target,
                "rates": rates,
                "intervals": intervals,
                "metrics": metrics,
                "hourly_price": hourly_price,
                "price_hike_detected": is_hike,
                "price_hike_pct": hike_pct,
            }

    def get_all_pools(
        self,
        region: str | None = None,
        family: str | None = None,
        watchlist_only: bool = False,
        search: str | None = None,
    ) -> list[PoolSummaryResponse]:
        """Query and filter summary statistics for monitored pools."""
        results: list[PoolSummaryResponse] = []

        for key, data in self._synthetic_pool_cache.items():
            target: InstancePoolTarget = data["target"]
            if region and target.region != region.strip().lower():
                continue
            if family and target.family != family.strip().lower():
                continue
            if watchlist_only and not target.is_watchlist:
                continue
            if search:
                s = search.strip().lower()
                if (
                    s not in target.region.lower()
                    and s not in target.zone.lower()
                    and s not in target.machine_type.lower()
                    and s not in (target.custom_label or "").lower()
                ):
                    continue

            metrics = data["metrics"]
            rates = [r.preemption_rate for r in data["rates"]]
            avg_30d = sum(rates) / len(rates) if rates else 0.0

            results.append(
                PoolSummaryResponse(
                    pool_key=key,
                    region=target.region,
                    zone=target.zone,
                    machine_type=target.machine_type,
                    family=target.family,
                    is_watchlist=target.is_watchlist,
                    custom_label=target.custom_label,
                    latest_rate=metrics["latest_rate"],
                    avg_7d_rate=metrics["recent_7d_rate"],
                    avg_30d_rate=round(avg_30d, 4),
                    hourly_price=data["hourly_price"],
                    severity=metrics["severity"],
                )
            )

        # Sort: watchlist first, then severity (CRITICAL, ELEVATED, STABLE), then pool_key
        severity_order = {"CRITICAL": 0, "ELEVATED": 1, "STABLE": 2}
        results.sort(
            key=lambda p: (
                0 if p.is_watchlist else 1,
                severity_order.get(p.severity, 2),
                p.pool_key,
            )
        )
        return results

    def get_anomalies(
        self,
        severity: str | None = None,
        region: str | None = None,
        watchlist_only: bool = False,
    ) -> list[AnomalyResponse]:
        """Fetch active regime shift anomalies with candidate pivot counts."""
        cache_key = f"anomalies:{severity}:{region}:{watchlist_only}"
        cached = get_cached(cache_key)
        if cached is not None:
            return cached

        # Prepare pools list for pivot matching
        pool_dicts = []
        for data in self._synthetic_pool_cache.values():
            t = data["target"]
            m = data["metrics"]
            pool_dicts.append(
                {
                    "region": t.region,
                    "zone": t.zone,
                    "machine_type": t.machine_type,
                    "family": t.family,
                    "severity": m["severity"],
                    "recent_7d_rate": m["recent_7d_rate"],
                    "hourly_price": data["hourly_price"],
                }
            )

        anomalies: list[AnomalyResponse] = []
        for key, data in self._synthetic_pool_cache.items():
            target: InstancePoolTarget = data["target"]
            metrics = data["metrics"]
            sev = metrics["severity"]

            if sev == "STABLE" and not data["price_hike_detected"]:
                continue

            if severity and sev != severity.upper():
                continue
            if region and target.region != region.strip().lower():
                continue
            if watchlist_only and not target.is_watchlist:
                continue

            # Calculate pivot options count
            pivots = find_pivot_candidates_for_pool(
                origin_pool={
                    "region": target.region,
                    "zone": target.zone,
                    "machine_type": target.machine_type,
                    "family": target.family,
                    "severity": sev,
                    "recent_7d_rate": metrics["recent_7d_rate"],
                    "hourly_price": data["hourly_price"],
                },
                all_pools=pool_dicts,
            )

            anomalies.append(
                AnomalyResponse(
                    pool_key=key,
                    region=target.region,
                    zone=target.zone,
                    machine_type=target.machine_type,
                    family=target.family,
                    is_watchlist=target.is_watchlist,
                    custom_label=target.custom_label,
                    latest_rate=metrics["latest_rate"],
                    recent_7d_rate=metrics["recent_7d_rate"],
                    baseline_rate=metrics["baseline_rate"],
                    rate_delta=metrics["rate_delta"],
                    z_score=metrics["z_score"],
                    hourly_price=data["hourly_price"],
                    severity=sev,
                    price_hike_detected=data["price_hike_detected"],
                    price_hike_pct=data["price_hike_pct"],
                    pivot_count=len(pivots),
                )
            )

        # Sort critical first, then Z-score descending
        severity_rank = {"CRITICAL": 0, "ELEVATED": 1, "STABLE": 2}
        anomalies.sort(key=lambda a: (severity_rank.get(a.severity, 2), -a.z_score))

        set_cached(cache_key, anomalies)
        return anomalies

    def get_pool_history(
        self,
        region: str,
        zone: str,
        machine_type: str,
    ) -> PoolHistoryResponse | None:
        """Fetch 30-day preemption points and price intervals for a specific pool."""
        key = f"{region.strip().lower()}/{zone.strip().lower()}/{machine_type.strip().lower()}"
        data = self._synthetic_pool_cache.get(key)
        if not data:
            return None

        target = data["target"]
        metrics = data["metrics"]

        return PoolHistoryResponse(
            pool_key=key,
            region=target.region,
            zone=target.zone,
            machine_type=target.machine_type,
            family=target.family,
            is_watchlist=target.is_watchlist,
            custom_label=target.custom_label,
            rates=data["rates"],
            intervals=data["intervals"],
            latest_rate=metrics["latest_rate"],
            recent_7d_rate=metrics["recent_7d_rate"],
            baseline_rate=metrics["baseline_rate"],
            rate_delta=metrics["rate_delta"],
            z_score=metrics["z_score"],
            severity=metrics["severity"],
            current_hourly_price=data["hourly_price"],
        )

    def get_pivot_recommendations(
        self,
        region: str,
        zone: str,
        machine_type: str,
    ) -> PivotRecommendationResponse | None:
        """Find and rank sibling zone and equivalent family pivots for a target pool."""
        key = f"{region.strip().lower()}/{zone.strip().lower()}/{machine_type.strip().lower()}"
        data = self._synthetic_pool_cache.get(key)
        if not data:
            return None

        target = data["target"]
        metrics = data["metrics"]

        pool_dicts = [
            {
                "region": d["target"].region,
                "zone": d["target"].zone,
                "machine_type": d["target"].machine_type,
                "family": d["target"].family,
                "severity": d["metrics"]["severity"],
                "recent_7d_rate": d["metrics"]["recent_7d_rate"],
                "hourly_price": d["hourly_price"],
            }
            for d in self._synthetic_pool_cache.values()
        ]

        origin_pool = {
            "region": target.region,
            "zone": target.zone,
            "machine_type": target.machine_type,
            "family": target.family,
            "severity": metrics["severity"],
            "recent_7d_rate": metrics["recent_7d_rate"],
            "hourly_price": data["hourly_price"],
        }

        candidates = find_pivot_candidates_for_pool(origin_pool, pool_dicts)

        return PivotRecommendationResponse(
            pool_key=key,
            origin_severity=metrics["severity"],
            pivots=candidates,
        )

    def add_watchlist_entry(self, req: WatchlistCreateRequest) -> list[str]:
        """Dynamically add custom watchlist targets to active monitoring."""
        entry = WatchlistEntry(
            name=req.name,
            region=req.region,
            zones=req.zones,
            machine_types=req.machine_types,
            alert_threshold_z=req.alert_threshold_z,
            alert_threshold_delta=req.alert_threshold_delta,
        )
        self._custom_watchlist_entries.append(entry)

        # Merge into watchlist
        self.watchlist.watchlist.append(entry)
        self._initialize_synthetic_dataset()

        # Invalidate cache
        from mindthespot.api.cache import clear_cache
        clear_cache()

        added_keys = []
        for mt in req.machine_types:
            for z in req.zones:
                added_keys.append(f"{req.region}/{z}/{mt}")
        return added_keys
