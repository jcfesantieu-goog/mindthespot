import logging
import os
import random
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

from mindthespot.analytics.pivot_rules import (
    find_pivot_candidates_for_pool,
)
from mindthespot.analytics.statistical import (
    compute_preemption_regime_shift,
    detect_price_step_change,
)
from mindthespot.api.cache import clear_cache, get_cached, set_cached
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

logger = logging.getLogger(__name__)


class SpotDataService:
    """Provides analytical spot data, regime shift metrics, and pivot fallbacks."""

    def __init__(
        self,
        catalog: CatalogConfig | None = None,
        watchlist: WatchlistConfig | None = None,
        pre_warm: bool = False,
        project_id: str | None = None,
    ) -> None:
        self.catalog = catalog or load_catalog()
        self.watchlist = watchlist or load_watchlist()
        self._custom_watchlist_entries: list[WatchlistEntry] = []
        self._pool_cache: dict[str, dict[str, Any]] = {}
        self._data_source: str = "synthetic"
        self._last_synced_at: datetime | None = None
        self._total_price_intervals: int = 0
        self._total_preemption_points: int = 0
        self._is_warming: bool = False
        self._lock = threading.Lock()

        # Seed initial synthetic dataset by default (safe instant startup)
        self._initialize_synthetic_dataset()

        if pre_warm:
            self.warm_cache_from_bigquery(project_id)

    @property
    def _synthetic_pool_cache(self) -> dict[str, dict[str, Any]]:
        return self._pool_cache

    @_synthetic_pool_cache.setter
    def _synthetic_pool_cache(self, value: dict[str, dict[str, Any]]) -> None:
        self._pool_cache = value


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

        self._data_source = "synthetic"
        self._last_synced_at = datetime.now(UTC)
        self._total_price_intervals = sum(len(d["intervals"]) for d in self._pool_cache.values())
        self._total_preemption_points = sum(len(d["rates"]) for d in self._pool_cache.values())

    def warm_cache_from_bigquery(self, project_id: str | None = None) -> bool:
        """Pre-warm in-memory cache directly from BigQuery tables and analytical views.

        Loads mindthespot_analytics.v_regime_shifts, mindthespot_raw.price_history,
        and mindthespot_raw.preemption_history into memory. Falls back to synthetic dataset
        if BigQuery is unavailable or unauthenticated.
        """
        pid = (
            project_id
            or os.getenv("GCP_PROJECT")
            or os.getenv("PROJECT_ID")
            or "jcf-mindthespot"
        )
        self._is_warming = True
        logger.info("Pre-warming MindTheSpot cache from BigQuery in project: %s", pid)

        try:
            from google.cloud import bigquery

            client = bigquery.Client(project=pid)

            def run_q(query: str):
                return list(client.query(query).result())

            q_shifts = f"""
            SELECT region, zone, machine_type, family, is_watchlist, custom_label,
                   recent_7d_rate, baseline_rate, rate_delta, z_score,
                   hourly_price, currency, price_hike_detected, severity
            FROM `{pid}.mindthespot_analytics.v_regime_shifts`
            """

            q_prices = f"""
            SELECT region, machine_type, interval_start, interval_end, hourly_price, currency
            FROM `{pid}.mindthespot_raw.price_history`
            ORDER BY region, machine_type, interval_start ASC
            """

            q_preempt = f"""
            SELECT region, zone, machine_type, telemetry_date, preemption_rate
            FROM `{pid}.mindthespot_raw.preemption_history`
            WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM `{pid}.mindthespot_raw.preemption_history`)
            ORDER BY region, zone, machine_type, telemetry_date ASC
            """

            with ThreadPoolExecutor(max_workers=3) as executor:
                fut_shifts = executor.submit(run_q, q_shifts)
                fut_prices = executor.submit(run_q, q_prices)
                fut_preempt = executor.submit(run_q, q_preempt)

                shifts = fut_shifts.result()
                prices = fut_prices.result()
                preempts = fut_preempt.result()

            price_map: dict[tuple[str, str], list[PriceIntervalRecord]] = defaultdict(list)
            for p in prices:
                reg = p.region.strip().lower()
                mt = p.machine_type.strip().lower()
                start_str = p.interval_start.isoformat() if p.interval_start else ""
                end_str = p.interval_end.isoformat() if p.interval_end else None
                price_map[(reg, mt)].append(
                    PriceIntervalRecord(
                        start_time=start_str,
                        end_time=end_str,
                        hourly_price=round(float(p.hourly_price), 6),
                        currency=p.currency or "USD",
                    )
                )

            preempt_map: dict[tuple[str, str, str], list[DailyPreemptionRate]] = defaultdict(list)
            for pr in preempts:
                reg = pr.region.strip().lower()
                zn = pr.zone.strip().lower()
                mt = pr.machine_type.strip().lower()
                d_str = pr.telemetry_date.isoformat() if pr.telemetry_date else ""
                preempt_map[(reg, zn, mt)].append(
                    DailyPreemptionRate(
                        date=d_str,
                        preemption_rate=round(float(pr.preemption_rate), 4),
                    )
                )

            new_cache: dict[str, dict[str, Any]] = {}
            for s in shifts:
                reg = s.region.strip().lower()
                zn = s.zone.strip().lower()
                mt = s.machine_type.strip().lower()
                key = f"{reg}/{zn}/{mt}"

                rates = preempt_map.get((reg, zn, mt), [])
                intervals = price_map.get((reg, mt), [])

                latest_rate = rates[-1].preemption_rate if rates else (s.recent_7d_rate or 0.0)

                target = InstancePoolTarget(
                    region=reg,
                    zone=zn,
                    machine_type=mt,
                    family=s.family or mt.split("-")[0],
                    is_watchlist=bool(s.is_watchlist),
                    custom_label=s.custom_label,
                )

                metrics = {
                    "latest_rate": round(float(latest_rate), 4),
                    "recent_7d_rate": round(float(s.recent_7d_rate or 0.0), 4),
                    "baseline_rate": round(float(s.baseline_rate or 0.0), 4),
                    "rate_delta": round(float(s.rate_delta or 0.0), 4),
                    "z_score": round(float(s.z_score or 0.0), 2),
                    "severity": s.severity or "STABLE",
                }

                current_price = float(
                    s.hourly_price
                    if s.hourly_price is not None
                    else (intervals[-1].hourly_price if intervals else 0.0)
                )

                price_hike_pct = 0.0
                if len(intervals) >= 2 and intervals[-2].hourly_price > 0:
                    prev_p = intervals[-2].hourly_price
                    price_hike_pct = round(((current_price - prev_p) / prev_p) * 100.0, 2)

                new_cache[key] = {
                    "target": target,
                    "rates": rates,
                    "intervals": intervals,
                    "metrics": metrics,
                    "hourly_price": round(current_price, 6),
                    "price_hike_detected": bool(s.price_hike_detected),
                    "price_hike_pct": price_hike_pct,
                }

            with self._lock:
                self._pool_cache = new_cache
                self._data_source = "bigquery"
                self._last_synced_at = datetime.now(UTC)
                self._total_price_intervals = len(prices)
                self._total_preemption_points = len(preempts)

            clear_cache()
            logger.info(
                "Successfully pre-warmed cache from BigQuery with %d pools (%d price intervals, %d daily rates)",
                len(new_cache),
                len(prices),
                len(preempts),
            )
            return True

        except Exception as exc:
            logger.warning(
                "Could not pre-warm cache from BigQuery (%s). Keeping active cache (source=%s).",
                exc,
                self._data_source,
            )
            if not self._pool_cache:
                self._initialize_synthetic_dataset()
            return False
        finally:
            self._is_warming = False

    def trigger_background_sync(self, project_id: str | None = None) -> None:
        """Spawns background thread to refresh cache asynchronously without blocking serving."""
        thread = threading.Thread(
            target=self.warm_cache_from_bigquery,
            args=(project_id,),
            daemon=True,
        )
        thread.start()

    def get_cache_status(self) -> dict[str, Any]:
        """Return cache metadata, source status, and row counts."""
        return {
            "source": self._data_source,
            "last_synced_at": self._last_synced_at.isoformat() if self._last_synced_at else None,
            "total_pools_cached": len(self._pool_cache),
            "total_price_intervals": self._total_price_intervals,
            "total_preemption_points": self._total_preemption_points,
            "is_warming": self._is_warming,
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
                    price_hike_detected=bool(data.get("price_hike_detected", False)),
                    price_hike_pct=float(data.get("price_hike_pct") or 0.0),
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
