"""Crawler extraction engine orchestrating concurrent ingestion of Spot metrics."""

import asyncio
import logging
from datetime import UTC, datetime

from mindthespot.config.loader import resolve_targets
from mindthespot.config.models import CatalogConfig, InstancePoolTarget, WatchlistConfig
from mindthespot.crawler.client import GCPCapacityHistoryClient
from mindthespot.crawler.models import (
    CrawlSummary,
    PreemptionSnapshotRecord,
    PriceSnapshotRecord,
)

logger = logging.getLogger(__name__)


class CrawlEngine:
    """Orchestrates concurrent fetching of preemption and price telemetry across target pools."""

    def __init__(
        self,
        client: GCPCapacityHistoryClient,
        catalog: CatalogConfig,
        watchlist: WatchlistConfig | None = None,
        project: str = "default-project",
    ) -> None:
        self.client = client
        self.catalog = catalog
        self.watchlist = watchlist
        self.project = project

    async def crawl_preemption_target(
        self,
        target: InstancePoolTarget,
        snapshot_date: str,
        crawled_at: str,
    ) -> PreemptionSnapshotRecord | None:
        """Fetch and summarize preemption rates for a single zonal instance pool."""
        try:
            rates = await self.client.fetch_preemption_history(
                project=self.project,
                region=target.region,
                zone=target.zone,
                machine_type=target.machine_type,
            )

            # Calculate basic rolling metrics
            latest_rate = rates[-1].preemption_rate if rates else 0.0
            rates_7d = [r.preemption_rate for r in rates[-7:]] if rates else []
            avg_7d = sum(rates_7d) / len(rates_7d) if rates_7d else 0.0
            rates_30d = [r.preemption_rate for r in rates] if rates else []
            avg_30d = sum(rates_30d) / len(rates_30d) if rates_30d else 0.0

            return PreemptionSnapshotRecord(
                snapshot_date=snapshot_date,
                crawled_at=crawled_at,
                region=target.region,
                zone=target.zone,
                machine_type=target.machine_type,
                family=target.family,
                rates=rates,
                latest_rate=round(latest_rate, 4),
                avg_7d_rate=round(avg_7d, 4),
                avg_30d_rate=round(avg_30d, 4),
                is_watchlist=target.is_watchlist,
                custom_label=target.custom_label,
            )
        except Exception as e:
            logger.error(
                "Error crawling preemption for %s/%s/%s: %s",
                target.region,
                target.zone,
                target.machine_type,
                e,
            )
            return None

    async def crawl_price_target(
        self,
        region: str,
        machine_type: str,
        family: str,
        snapshot_date: str,
        crawled_at: str,
    ) -> PriceSnapshotRecord | None:
        """Fetch and summarize price history for a regional machine type."""
        try:
            intervals = await self.client.fetch_price_history(
                project=self.project,
                region=region,
                machine_type=machine_type,
            )

            # Find active price: interval with end_time None or the most recent interval
            current_price = 0.0
            currency = "USD"
            if intervals:
                active_interval = next((i for i in intervals if i.end_time is None), intervals[-1])
                current_price = active_interval.hourly_price
                currency = active_interval.currency

            return PriceSnapshotRecord(
                snapshot_date=snapshot_date,
                crawled_at=crawled_at,
                region=region,
                machine_type=machine_type,
                family=family,
                intervals=intervals,
                current_hourly_price=current_price,
                currency=currency,
            )
        except Exception as e:
            logger.error(
                "Error crawling price for %s/%s: %s",
                region,
                machine_type,
                e,
            )
            return None

    async def run(
        self,
        region_filter: str | None = None,
        family_filter: str | None = None,
    ) -> tuple[list[PreemptionSnapshotRecord], list[PriceSnapshotRecord], CrawlSummary]:
        """Execute full crawl across configured targets with optional filtering."""
        started_at = datetime.now(UTC)
        snapshot_date = started_at.strftime("%Y-%m-%d")
        crawled_at = started_at.isoformat()

        all_targets = resolve_targets(self.catalog, self.watchlist)

        # Apply optional filters
        if region_filter:
            rf = region_filter.strip().lower()
            all_targets = [t for t in all_targets if t.region == rf]
        if family_filter:
            ff = family_filter.strip().lower()
            all_targets = [t for t in all_targets if t.family == ff]

        # 1. Dispatch Preemption tasks (zonal)
        preempt_tasks = [
            self.crawl_preemption_target(target, snapshot_date, crawled_at)
            for target in all_targets
        ]

        # 2. Dispatch Price tasks (regional deduplication)
        unique_price_keys: set[tuple[str, str, str]] = {
            (t.region, t.machine_type, t.family) for t in all_targets
        }
        price_tasks = [
            self.crawl_price_target(region, machine_type, family, snapshot_date, crawled_at)
            for (region, machine_type, family) in unique_price_keys
        ]

        # Run concurrently
        preempt_results, price_results = await asyncio.gather(
            asyncio.gather(*preempt_tasks),
            asyncio.gather(*price_tasks),
        )

        valid_preempt = [r for r in preempt_results if r is not None]
        valid_price = [r for r in price_results if r is not None]
        failed_count = (len(preempt_tasks) - len(valid_preempt)) + (len(price_tasks) - len(valid_price))

        completed_at = datetime.now(UTC)
        duration = (completed_at - started_at).total_seconds()

        summary = CrawlSummary(
            snapshot_date=snapshot_date,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=round(duration, 2),
            total_preemption_pools=len(all_targets),
            total_price_pools=len(unique_price_keys),
            successful_preemption_queries=len(valid_preempt),
            successful_price_queries=len(valid_price),
            failed_queries=failed_count,
        )

        return valid_preempt, valid_price, summary
