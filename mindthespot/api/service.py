import json
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
    WatchlistSyncRequest,
    WatchlistSyncResponse,
)
from mindthespot.config.loader import load_catalog, load_watchlist, resolve_targets
from mindthespot.config.models import (
    CatalogConfig,
    InstancePoolTarget,
    WatchlistConfig,
    WatchlistEntry,
)
from mindthespot.crawler.models import DailyPreemptionRate, PriceIntervalRecord
from mindthespot.storage.pricing_seeder import compute_on_demand_price

logger = logging.getLogger(__name__)


class SpotDataService:
    """Provides analytical spot data, regime shift metrics, and pivot fallbacks."""

    def __init__(
        self,
        catalog: CatalogConfig | None = None,
        watchlist: WatchlistConfig | None = None,
        pre_warm: bool = False,
        project_id: str | None = None,
        initialize_synthetic: bool = True,
        bq_storage: Any | None = None,
    ) -> None:
        self.catalog = catalog or load_catalog()
        self.watchlist = watchlist or load_watchlist()
        self.project_id = (
            project_id
            or os.getenv("GCP_PROJECT")
            or os.getenv("PROJECT_ID")
            or os.getenv("GCP_PROJECT_ID")
            or "jcf-mindthespot"
        )
        self._bq_storage = bq_storage
        self._custom_watchlist_entries: list[WatchlistEntry] = []
        self._pool_cache: dict[str, dict[str, Any]] = {}
        self._data_source: str = "synthetic"
        self._last_synced_at: datetime | None = None
        self._total_price_intervals: int = 0
        self._total_preemption_points: int = 0
        self._is_warming: bool = False
        self._lock = threading.Lock()

        # Seed initial synthetic dataset by default (safe instant startup)
        if initialize_synthetic:
            self._initialize_synthetic_dataset()

        if pre_warm:
            self.warm_cache_from_bigquery(self.project_id)

    @property
    def bq_storage(self) -> Any:
        """BigQuery storage client instance for persistent watchlist storage."""
        if self._bq_storage is None:
            if os.getenv("DISABLE_BIGQUERY_STORAGE", "false").lower() in ("true", "1", "yes"):
                return None
            try:
                from mindthespot.storage.bigquery_client import BigQueryStorageClient

                self._bq_storage = BigQueryStorageClient(
                    project=self.project_id,
                    dataset=os.getenv("BIGQUERY_DATASET_RAW", "mindthespot_raw"),
                )
            except Exception as exc:
                logger.warning("Could not initialize BigQueryStorageClient: %s", exc)
                return None
        return self._bq_storage

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
            # Inject a -15% price drop for c3d in europe-west1
            has_price_drop = target.region == "europe-west1" and target.family == "c3d"

            if has_price_hike:
                prev_price = round(hourly_price * 0.88, 4)
            elif has_price_drop:
                prev_price = round(hourly_price * 1.15, 4)
            else:
                prev_price = hourly_price

            intervals = [
                PriceIntervalRecord(
                    start_time=(base_date - timedelta(days=335)).isoformat(),
                    end_time=base_date.isoformat() if (has_price_hike or has_price_drop) else None,
                    hourly_price=prev_price,
                    currency="USD",
                )
            ]
            if has_price_hike or has_price_drop:
                intervals.append(
                    PriceIntervalRecord(
                        start_time=base_date.isoformat(),
                        end_time=None,
                        hourly_price=hourly_price,
                        currency="USD",
                    )
                )

            is_hike, hike_pct = detect_price_step_change(
                hourly_price, prev_price if (has_price_hike or has_price_drop) else None
            )
            price_change_pct = (
                round(((hourly_price - prev_price) / prev_price) * 100.0, 2)
                if prev_price > 0
                else 0.0
            )

            od_price = compute_on_demand_price(target.region, target.machine_type, target.family)
            discount_pct = (
                round(((od_price - hourly_price) / od_price) * 100.0, 1)
                if od_price > 0
                else 0.0
            )

            self._synthetic_pool_cache[key] = {
                "target": target,
                "rates": rates,
                "intervals": intervals,
                "metrics": metrics,
                "hourly_price": hourly_price,
                "ondemand_hourly_price": od_price,
                "spot_discount_pct": discount_pct,
                "price_hike_detected": is_hike,
                "price_drop_detected": has_price_drop or (price_change_pct <= -5.0),
                "price_hike_pct": hike_pct,
                "price_change_pct": price_change_pct,
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
            or os.getenv("GCP_PROJECT_ID")
            or "jcf-mindthespot"
        )
        ds_raw = os.getenv("BIGQUERY_DATASET_RAW", "mindthespot_raw")
        ds_analytics = os.getenv("BIGQUERY_DATASET_ANALYTICS", "mindthespot_analytics")
        self._is_warming = True
        logger.info(
            "Pre-warming MindTheSpot cache from BigQuery in project: %s (raw: %s, analytics: %s)",
            pid,
            ds_raw,
            ds_analytics,
        )

        try:
            from google.cloud import bigquery

            client = bigquery.Client(project=pid)

            def run_q(query: str):
                return list(client.query(query).result())

            q_shifts = f"""
            SELECT region, zone, machine_type, family, is_watchlist, custom_label,
                   recent_7d_rate, baseline_rate, rate_delta, z_score,
                   hourly_price, currency, ondemand_hourly_price, spot_discount_pct,
                   price_hike_detected, severity
            FROM `{pid}.{ds_analytics}.v_regime_shifts`
            """

            q_prices = f"""
            WITH latest_snapshot AS (
                SELECT MAX(snapshot_date) AS max_snapshot_date
                FROM `{pid}.{ds_raw}.price_history`
            ),
            deduped AS (
                SELECT region, machine_type, interval_start, interval_end, hourly_price, currency,
                       ROW_NUMBER() OVER (
                           PARTITION BY region, machine_type, interval_start
                           ORDER BY crawled_at DESC
                       ) AS rn
                FROM `{pid}.{ds_raw}.price_history`
                WHERE snapshot_date = (SELECT max_snapshot_date FROM latest_snapshot)
            )
            SELECT region, machine_type, interval_start, interval_end, hourly_price, currency
            FROM deduped
            WHERE rn = 1
            ORDER BY region, machine_type, interval_start ASC
            """

            q_preempt = f"""
            WITH latest_snapshot AS (
                SELECT MAX(snapshot_date) AS max_snapshot_date
                FROM `{pid}.{ds_raw}.preemption_history`
            ),
            deduped AS (
                SELECT region, zone, machine_type, telemetry_date, preemption_rate,
                       ROW_NUMBER() OVER (
                           PARTITION BY region, zone, machine_type, telemetry_date
                           ORDER BY crawled_at DESC
                       ) AS rn
                FROM `{pid}.{ds_raw}.preemption_history`
                WHERE snapshot_date = (SELECT max_snapshot_date FROM latest_snapshot)
            )
            SELECT region, zone, machine_type, telemetry_date, preemption_rate
            FROM deduped
            WHERE rn = 1
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

            # Hydrate user watchlists from BigQuery persistent table
            starred_pools_bq: dict[str, str | None] = {}
            try:
                if self.bq_storage is not None:
                    bq_rows = self.bq_storage.fetch_user_watchlists()
                    for r in bq_rows:
                        wtype = r.get("watchlist_type")
                        if wtype == "WORKLOAD_TARGET":
                            zones = json.loads(r["zones_json"]) if r.get("zones_json") else []
                            machine_types = (
                                json.loads(r["machine_types_json"])
                                if r.get("machine_types_json")
                                else [r["machine_type"]]
                                if r.get("machine_type")
                                else []
                            )
                            entry = WatchlistEntry(
                                name=r.get("target_name"),
                                region=r["region"],
                                zones=zones,
                                machine_types=machine_types,
                                alert_threshold_z=r.get("alert_threshold_z"),
                                alert_threshold_delta=r.get("alert_threshold_delta"),
                            )
                            if not any(
                                e.name == entry.name and e.region == entry.region
                                for e in self.watchlist.watchlist
                            ):
                                self.watchlist.watchlist.append(entry)
                            if not any(
                                e.name == entry.name and e.region == entry.region
                                for e in self._custom_watchlist_entries
                            ):
                                self._custom_watchlist_entries.append(entry)
                        elif wtype == "STARRED_POOL":
                            r_reg = str(r.get("region") or "").strip().lower()
                            r_zone = str(r.get("zone") or "").strip().lower()
                            r_mt = str(r.get("machine_type") or "").strip().lower()
                            if r_reg and r_zone and r_mt:
                                starred_pools_bq[f"{r_reg}/{r_zone}/{r_mt}"] = r.get("custom_label")
            except Exception as wl_exc:
                logger.warning("Could not hydrate user watchlists during BigQuery pre-warm: %s", wl_exc)

            new_cache: dict[str, dict[str, Any]] = {}
            for s in shifts:
                reg = s.region.strip().lower()
                zn = s.zone.strip().lower()
                mt = s.machine_type.strip().lower()
                key = f"{reg}/{zn}/{mt}"

                rates = preempt_map.get((reg, zn, mt), [])
                intervals = price_map.get((reg, mt), [])

                latest_rate = rates[-1].preemption_rate if rates else (s.recent_7d_rate or 0.0)

                is_wl = bool(s.is_watchlist) or (key in starred_pools_bq)
                custom_lbl = s.custom_label or starred_pools_bq.get(key)

                # Check workload targets
                for w_entry in self.watchlist.watchlist:
                    if reg == w_entry.region.lower():
                        zone_ok = not w_entry.zones or zn in [z.lower() for z in w_entry.zones]
                        mt_ok = not w_entry.machine_types or mt in [m.lower() for m in w_entry.machine_types]
                        if zone_ok and mt_ok:
                            is_wl = True
                            if w_entry.name:
                                custom_lbl = w_entry.name
                            break

                # Preserve runtime cache if active
                if key in self._pool_cache and self._pool_cache[key]["target"].is_watchlist:
                    is_wl = True
                    custom_lbl = self._pool_cache[key]["target"].custom_label or custom_lbl

                target = InstancePoolTarget(
                    region=reg,
                    zone=zn,
                    machine_type=mt,
                    family=s.family or mt.split("-")[0],
                    is_watchlist=is_wl,
                    custom_label=custom_lbl,
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

                price_change_pct = 0.0
                if getattr(s, "price_change_pct", None) is not None:
                    price_change_pct = float(s.price_change_pct)
                elif len(intervals) >= 2 and intervals[-2].hourly_price > 0:
                    prev_p = intervals[-2].hourly_price
                    price_change_pct = round(((current_price - prev_p) / prev_p) * 100.0, 2)

                price_hike_detected = bool(getattr(s, "price_hike_detected", False)) or (
                    price_change_pct >= 5.0
                )
                price_drop_detected = bool(getattr(s, "price_drop_detected", False)) or (
                    price_change_pct <= -5.0
                )

                od_price = (
                    float(s.ondemand_hourly_price)
                    if getattr(s, "ondemand_hourly_price", None) is not None
                    else compute_on_demand_price(reg, mt, target.family)
                )
                discount_pct = (
                    float(s.spot_discount_pct)
                    if getattr(s, "spot_discount_pct", None) is not None
                    else (
                        round(((od_price - current_price) / od_price) * 100.0, 1)
                        if od_price > 0
                        else None
                    )
                )

                new_cache[key] = {
                    "target": target,
                    "rates": rates,
                    "intervals": intervals,
                    "metrics": metrics,
                    "hourly_price": round(current_price, 6),
                    "ondemand_hourly_price": od_price,
                    "spot_discount_pct": discount_pct,
                    "price_hike_detected": price_hike_detected,
                    "price_drop_detected": price_drop_detected,
                    "price_hike_pct": price_change_pct if price_change_pct > 0 else 0.0,
                    "price_change_pct": price_change_pct,
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
            logger.error(
                "Could not pre-warm cache from BigQuery: %s. Keeping active cache (source=%s).",
                exc,
                self._data_source,
                exc_info=True,
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
                    ondemand_hourly_price=data.get("ondemand_hourly_price"),
                    spot_discount_pct=data.get("spot_discount_pct"),
                    severity=metrics["severity"],
                    price_hike_detected=bool(data.get("price_hike_detected", False)),
                    price_drop_detected=bool(data.get("price_drop_detected", False)),
                    price_change_pct=float(data.get("price_change_pct") or 0.0),
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
        price_filter: str | None = None,
    ) -> list[AnomalyResponse]:
        """Fetch active regime shift anomalies with candidate pivot counts."""
        cache_key = f"anomalies:{severity}:{region}:{watchlist_only}:{price_filter}"
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
                    "ondemand_hourly_price": data.get("ondemand_hourly_price"),
                    "spot_discount_pct": data.get("spot_discount_pct"),
                }
            )

        anomalies: list[AnomalyResponse] = []
        for key, data in self._synthetic_pool_cache.items():
            target: InstancePoolTarget = data["target"]
            metrics = data["metrics"]
            sev = metrics["severity"]
            is_hike = bool(data.get("price_hike_detected", False))
            is_drop = bool(data.get("price_drop_detected", False))

            if sev == "STABLE" and not is_hike and not is_drop:
                continue

            if severity and sev != severity.upper():
                continue
            if region and target.region != region.strip().lower():
                continue
            if watchlist_only and not target.is_watchlist:
                continue

            if price_filter:
                pf = price_filter.strip().upper()
                if pf == "HIKE" and not is_hike:
                    continue
                if pf == "DROP" and not is_drop:
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
                    "ondemand_hourly_price": data.get("ondemand_hourly_price"),
                    "spot_discount_pct": data.get("spot_discount_pct"),
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
                    ondemand_hourly_price=data.get("ondemand_hourly_price"),
                    spot_discount_pct=data.get("spot_discount_pct"),
                    severity=sev,
                    price_hike_detected=is_hike,
                    price_drop_detected=is_drop,
                    price_hike_pct=float(data.get("price_hike_pct") or 0.0),
                    price_change_pct=float(data.get("price_change_pct") or 0.0),
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
            ondemand_hourly_price=data.get("ondemand_hourly_price"),
            spot_discount_pct=data.get("spot_discount_pct"),
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
                "ondemand_hourly_price": d.get("ondemand_hourly_price"),
                "spot_discount_pct": d.get("spot_discount_pct"),
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
            "ondemand_hourly_price": data.get("ondemand_hourly_price"),
            "spot_discount_pct": data.get("spot_discount_pct"),
        }

        candidates = find_pivot_candidates_for_pool(origin_pool, pool_dicts)

        return PivotRecommendationResponse(
            pool_key=key,
            origin_severity=metrics["severity"],
            pivots=candidates,
        )

    def add_watchlist_entry(
        self,
        req: WatchlistCreateRequest,
        user_email: str | None = None,
    ) -> list[str]:
        """Dynamically add custom watchlist targets to active monitoring and persist to BigQuery."""
        email = user_email or "default"
        entry = WatchlistEntry(
            name=req.name,
            region=req.region,
            zones=req.zones,
            machine_types=req.machine_types,
            alert_threshold_z=req.alert_threshold_z,
            alert_threshold_delta=req.alert_threshold_delta,
        )
        added_keys = []
        with self._lock:
            if not any(
                e.name == entry.name and e.region == entry.region
                for e in self._custom_watchlist_entries
            ):
                self._custom_watchlist_entries.append(entry)

            if not any(
                e.name == entry.name and e.region == entry.region
                for e in self.watchlist.watchlist
            ):
                self.watchlist.watchlist.append(entry)

            for _key, data in self._pool_cache.items():
                target = data.get("target")
                if target and target.region.lower() == req.region.lower():
                    zone_ok = not req.zones or target.zone.lower() in [z.lower() for z in req.zones]
                    mt_ok = not req.machine_types or target.machine_type.lower() in [
                        m.lower() for m in req.machine_types
                    ]
                    if zone_ok and mt_ok:
                        target.is_watchlist = True
                        if req.name:
                            target.custom_label = req.name
                        added_keys.append(target.pool_key)

        clear_cache()

        # Persist to BigQuery user_watchlists table
        if self.bq_storage is not None:
            now_iso = datetime.now(UTC).isoformat()
            row = {
                "user_email": email,
                "watchlist_type": "WORKLOAD_TARGET",
                "target_name": req.name,
                "region": req.region,
                "zone": None,
                "machine_type": None,
                "zones_json": json.dumps(req.zones) if req.zones else None,
                "machine_types_json": json.dumps(req.machine_types) if req.machine_types else None,
                "custom_label": req.name,
                "alert_threshold_z": req.alert_threshold_z,
                "alert_threshold_delta": req.alert_threshold_delta,
                "is_active": True,
                "updated_at": now_iso,
            }
            try:
                self.bq_storage.save_user_watchlist_entries([row])
            except Exception as exc:
                logger.warning("Failed to persist watchlist entry to BigQuery: %s", exc)

        return added_keys

    def toggle_watchlist_pool(
        self,
        region: str,
        zone: str,
        machine_type: str,
        is_watchlist: bool,
        custom_label: str | None = None,
        user_email: str | None = None,
    ) -> bool:
        """Toggle watchlist flag and custom label on an individual pool and persist to BigQuery."""
        email = user_email or "default"
        reg = region.strip().lower()
        zn = zone.strip().lower()
        mt = machine_type.strip().lower()
        key = f"{reg}/{zn}/{mt}"
        with self._lock:
            if key in self._pool_cache:
                self._pool_cache[key]["target"].is_watchlist = is_watchlist
                if custom_label:
                    self._pool_cache[key]["target"].custom_label = custom_label
                elif not is_watchlist:
                    self._pool_cache[key]["target"].custom_label = None

        clear_cache()

        # Persist to BigQuery user_watchlists table
        if self.bq_storage is not None:
            now_iso = datetime.now(UTC).isoformat()
            row = {
                "user_email": email,
                "watchlist_type": "STARRED_POOL",
                "target_name": None,
                "region": reg,
                "zone": zn,
                "machine_type": mt,
                "zones_json": None,
                "machine_types_json": None,
                "custom_label": custom_label,
                "alert_threshold_z": None,
                "alert_threshold_delta": None,
                "is_active": is_watchlist,
                "updated_at": now_iso,
            }
            try:
                self.bq_storage.save_user_watchlist_entries([row])
            except Exception as exc:
                logger.warning("Failed to persist toggle pool to BigQuery: %s", exc)

        return True

    def remove_watchlist_pool(
        self,
        region: str,
        zone: str,
        machine_type: str,
        user_email: str | None = None,
    ) -> bool:
        """Remove a pool from watchlist."""
        return self.toggle_watchlist_pool(
            region, zone, machine_type, is_watchlist=False, user_email=user_email
        )

    def remove_watchlist_target(
        self,
        name: str | None,
        region: str,
        user_email: str | None = None,
    ) -> bool:
        """Remove an entire named or regional watchlist entry and reset associated pools."""
        email = user_email or "default"
        with self._lock:
            matched = [
                e
                for e in self.watchlist.watchlist
                if (e.name == name or (not name and not e.name)) and e.region == region
            ]
            self.watchlist.watchlist = [
                e
                for e in self.watchlist.watchlist
                if not ((e.name == name or (not name and not e.name)) and e.region == region)
            ]
            self._custom_watchlist_entries = [
                e
                for e in self._custom_watchlist_entries
                if not ((e.name == name or (not name and not e.name)) and e.region == region)
            ]
            for entry in matched:
                for _key, data in self._pool_cache.items():
                    target = data.get("target")
                    if target and target.region == entry.region:
                        zone_ok = not entry.zones or target.zone in entry.zones
                        mt_ok = not entry.machine_types or target.machine_type in entry.machine_types
                        if zone_ok and mt_ok:
                            target.is_watchlist = False
                            target.custom_label = None

        clear_cache()

        # Persist soft-deletion to BigQuery user_watchlists table
        if self.bq_storage is not None:
            now_iso = datetime.now(UTC).isoformat()
            row = {
                "user_email": email,
                "watchlist_type": "WORKLOAD_TARGET",
                "target_name": name,
                "region": region,
                "zone": None,
                "machine_type": None,
                "zones_json": None,
                "machine_types_json": None,
                "custom_label": None,
                "alert_threshold_z": None,
                "alert_threshold_delta": None,
                "is_active": False,
                "updated_at": now_iso,
            }
            try:
                self.bq_storage.save_user_watchlist_entries([row])
            except Exception as exc:
                logger.warning("Failed to persist target deletion to BigQuery: %s", exc)

        return True

    def get_watchlist_state(self, user_email: str | None = None) -> WatchlistSyncResponse:
        """Return the consolidated watchlist entries, starred pools, and custom labels."""
        starred: list[str] = []
        labels: dict[str, str] = {}
        with self._lock:
            for key, data in self._pool_cache.items():
                target = data.get("target")
                if target and target.is_watchlist:
                    starred.append(key)
                    if target.custom_label:
                        labels[key] = target.custom_label

        return WatchlistSyncResponse(
            status="success",
            entries=list(self.watchlist.watchlist),
            starred_pools=starred,
            custom_labels=labels,
        )

    def sync_watchlist(
        self,
        req: WatchlistSyncRequest,
        user_email: str | None = None,
    ) -> WatchlistSyncResponse:
        """Reconcile and synchronize client-side watchlist state with BigQuery and in-memory cache."""
        email = user_email or "default"
        now_iso = datetime.now(UTC).isoformat()
        bq_rows_to_save: list[dict[str, Any]] = []

        # 1. Fetch current active state from BigQuery
        bq_rows = []
        try:
            if self.bq_storage is not None:
                bq_rows = self.bq_storage.fetch_user_watchlists(user_email=email)
        except Exception as exc:
            logger.warning("Could not fetch watchlists from BigQuery during sync: %s", exc)

        # Build maps from BigQuery
        bq_workloads: dict[str, WatchlistEntry] = {}
        bq_starred: set[str] = set()
        bq_labels: dict[str, str] = {}

        for row in bq_rows:
            wtype = row.get("watchlist_type")
            if wtype == "WORKLOAD_TARGET":
                w_name = row.get("target_name") or ""
                w_reg = row.get("region")
                w_key = f"{w_name}::{w_reg}"
                zones = json.loads(row["zones_json"]) if row.get("zones_json") else []
                machine_types = (
                    json.loads(row["machine_types_json"])
                    if row.get("machine_types_json")
                    else [row["machine_type"]]
                    if row.get("machine_type")
                    else []
                )
                bq_workloads[w_key] = WatchlistEntry(
                    name=row.get("target_name"),
                    region=w_reg,
                    zones=zones,
                    machine_types=machine_types,
                    alert_threshold_z=row.get("alert_threshold_z"),
                    alert_threshold_delta=row.get("alert_threshold_delta"),
                )
            elif wtype == "STARRED_POOL":
                reg = str(row.get("region") or "").strip().lower()
                z = str(row.get("zone") or "").strip().lower()
                mt = str(row.get("machine_type") or "").strip().lower()
                pool_key = f"{reg}/{z}/{mt}"
                bq_starred.add(pool_key)
                if row.get("custom_label"):
                    bq_labels[pool_key] = row["custom_label"]

        # Merge client entries into BigQuery if missing
        for client_entry in req.entries:
            c_key = f"{client_entry.name or ''}::{client_entry.region}"
            if c_key not in bq_workloads:
                bq_workloads[c_key] = client_entry
                bq_rows_to_save.append(
                    {
                        "user_email": email,
                        "watchlist_type": "WORKLOAD_TARGET",
                        "target_name": client_entry.name,
                        "region": client_entry.region,
                        "zone": None,
                        "machine_type": None,
                        "zones_json": json.dumps(client_entry.zones) if client_entry.zones else None,
                        "machine_types_json": json.dumps(client_entry.machine_types)
                        if client_entry.machine_types
                        else None,
                        "custom_label": client_entry.name,
                        "alert_threshold_z": client_entry.alert_threshold_z,
                        "alert_threshold_delta": client_entry.alert_threshold_delta,
                        "is_active": True,
                        "updated_at": now_iso,
                    }
                )

        # Merge client starred pools into BigQuery if missing
        for pool_key in req.starred_pools:
            pk = pool_key.lower().strip()
            if pk not in bq_starred:
                bq_starred.add(pk)
                parts = pk.split("/")
                if len(parts) == 3:
                    reg, z, mt = parts
                    lbl = req.custom_labels.get(pk) or req.custom_labels.get(pool_key)
                    if lbl:
                        bq_labels[pk] = lbl
                    bq_rows_to_save.append(
                        {
                            "user_email": email,
                            "watchlist_type": "STARRED_POOL",
                            "target_name": None,
                            "region": reg,
                            "zone": z,
                            "machine_type": mt,
                            "zones_json": None,
                            "machine_types_json": None,
                            "custom_label": lbl,
                            "alert_threshold_z": None,
                            "alert_threshold_delta": None,
                            "is_active": True,
                            "updated_at": now_iso,
                        }
                    )

        # Save any newly discovered rows to BigQuery
        if bq_rows_to_save and self.bq_storage is not None:
            try:
                self.bq_storage.save_user_watchlist_entries(bq_rows_to_save)
            except Exception as exc:
                logger.warning("Could not persist synced watchlists to BigQuery: %s", exc)

        final_entries = list(bq_workloads.values())
        final_starred = list(bq_starred)
        final_labels = {**req.custom_labels, **bq_labels}

        with self._lock:
            for entry in final_entries:
                if not any(
                    e.name == entry.name and e.region == entry.region
                    for e in self.watchlist.watchlist
                ):
                    self.watchlist.watchlist.append(entry)
                if not any(
                    e.name == entry.name and e.region == entry.region
                    for e in self._custom_watchlist_entries
                ):
                    self._custom_watchlist_entries.append(entry)

            for key, data in self._pool_cache.items():
                target = data.get("target")
                if not target:
                    continue
                if key.lower() in bq_starred:
                    target.is_watchlist = True
                    if key.lower() in final_labels:
                        target.custom_label = final_labels[key.lower()]
                else:
                    for entry in final_entries:
                        if target.region.lower() == entry.region.lower():
                            zone_ok = not entry.zones or target.zone.lower() in [
                                z.lower() for z in entry.zones
                            ]
                            mt_ok = not entry.machine_types or target.machine_type.lower() in [
                                m.lower() for m in entry.machine_types
                            ]
                            if zone_ok and mt_ok:
                                target.is_watchlist = True
                                if entry.name:
                                    target.custom_label = entry.name
                                break

        clear_cache()

        return WatchlistSyncResponse(
            status="success",
            entries=final_entries,
            starred_pools=final_starred,
            custom_labels=final_labels,
        )
