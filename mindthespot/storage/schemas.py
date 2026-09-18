"""BigQuery schema definitions and row transformation helpers."""

from typing import Any

from google.cloud import bigquery

from mindthespot.crawler.models import (
    PreemptionSnapshotRecord,
    PriceSnapshotRecord,
)

PREEMPTION_TABLE_SCHEMA = [
    bigquery.SchemaField("snapshot_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("crawled_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("region", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("zone", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("machine_type", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("family", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("telemetry_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("preemption_rate", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("is_watchlist", "BOOL", mode="NULLABLE"),
    bigquery.SchemaField("custom_label", "STRING", mode="NULLABLE"),
]

PRICE_TABLE_SCHEMA = [
    bigquery.SchemaField("snapshot_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("crawled_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("region", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("machine_type", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("family", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("interval_start", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("interval_end", "TIMESTAMP", mode="NULLABLE"),
    bigquery.SchemaField("hourly_price", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("currency", "STRING", mode="REQUIRED"),
]

ON_DEMAND_PRICING_TABLE_SCHEMA = [
    bigquery.SchemaField("region", "STRING", mode="REQUIRED", description="GCP region identifier"),
    bigquery.SchemaField("machine_type", "STRING", mode="REQUIRED", description="GCP machine type"),
    bigquery.SchemaField("family", "STRING", mode="REQUIRED", description="Machine family prefix"),
    bigquery.SchemaField("vcpus", "INTEGER", mode="REQUIRED", description="Number of guest vCPUs"),
    bigquery.SchemaField("memory_gb", "FLOAT64", mode="REQUIRED", description="Memory in GiB"),
    bigquery.SchemaField("hourly_price", "FLOAT64", mode="REQUIRED", description="Public on-demand hourly price"),
    bigquery.SchemaField("currency", "STRING", mode="REQUIRED", description="Currency code"),
    bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED", description="UTC timestamp of pricing reference update"),
]


def transform_preemption_records_to_rows(
    records: list[PreemptionSnapshotRecord],
) -> list[dict[str, Any]]:
    """Transform snapshot preemption records into BigQuery table rows."""
    rows: list[dict[str, Any]] = []
    for record in records:
        for daily in record.rates:
            rows.append(
                {
                    "snapshot_date": record.snapshot_date,
                    "crawled_at": record.crawled_at,
                    "region": record.region,
                    "zone": record.zone,
                    "machine_type": record.machine_type,
                    "family": record.family,
                    "telemetry_date": daily.date,
                    "preemption_rate": daily.preemption_rate,
                    "is_watchlist": record.is_watchlist,
                    "custom_label": record.custom_label,
                }
            )
    return rows


def transform_price_records_to_rows(
    records: list[PriceSnapshotRecord],
) -> list[dict[str, Any]]:
    """Transform snapshot price records into BigQuery table rows."""
    rows: list[dict[str, Any]] = []
    for record in records:
        for interval in record.intervals:
            rows.append(
                {
                    "snapshot_date": record.snapshot_date,
                    "crawled_at": record.crawled_at,
                    "region": record.region,
                    "machine_type": record.machine_type,
                    "family": record.family,
                    "interval_start": interval.start_time,
                    "interval_end": interval.end_time,
                    "hourly_price": interval.hourly_price,
                    "currency": interval.currency,
                }
            )
    return rows
