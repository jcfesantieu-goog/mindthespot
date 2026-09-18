"""Seed and maintain GCP Compute Engine public on-demand list pricing in BigQuery."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from google.cloud import bigquery

from mindthespot.config.loader import load_catalog

logger = logging.getLogger(__name__)

# Base on-demand hourly rate per vCPU (including standard 4 GiB RAM per core) in standard US regions (USD)
FAMILY_BASE_VCPU_RATES: dict[str, float] = {
    "c4a": 0.04508,  # Google Axion (Arm Neoverse-V2)
    "c4d": 0.04820,  # AMD Turin (5th Gen EPYC)
    "c3d": 0.04650,  # AMD Genoa (4th Gen EPYC)
    "c3": 0.05150,   # Intel 4th Gen Xeon (Sapphire Rapids)
    "c2": 0.05220,   # Intel 2nd Gen Xeon (Cascade Lake)
    "n4": 0.04600,   # Intel 5th Gen Xeon (Emerald Rapids)
    "n2": 0.04880,   # Intel Xeon Scalable (Ice Lake)
    "n2d": 0.04250,  # AMD EPYC Milan/Rome
    "t2d": 0.04220,  # AMD EPYC Milan Scale-Out
    "t2a": 0.03850,  # Ampere Altra Arm
    "e2": 0.03350,   # Cost-Optimized Burstable
}

# Regional pricing tier multipliers relative to base US tier
REGIONAL_MULTIPLIERS: dict[str, float] = {
    # US Tier 1
    "us-central1": 1.00,
    "us-east1": 1.00,
    "us-east4": 1.00,
    "us-west1": 1.00,
    # US Tier 2
    "us-west2": 1.10,
    "us-west3": 1.10,
    "us-west4": 1.10,
    "us-south1": 1.10,
    # Europe Tier 1
    "europe-west1": 1.10,
    "europe-west4": 1.10,
    # Europe Tier 2
    "europe-west2": 1.15,
    "europe-west3": 1.15,
    "europe-west9": 1.15,
    "europe-north1": 1.15,
    "europe-central2": 1.15,
    "europe-southwest1": 1.15,
    "europe-west8": 1.15,
    "europe-west12": 1.15,
    # Europe Tier 3 (High cost)
    "europe-west6": 1.25,
    # Asia Tier 1
    "asia-east1": 1.10,
    "asia-southeast1": 1.10,
    # Asia Tier 2
    "asia-east2": 1.20,
    "asia-northeast1": 1.20,
    "asia-northeast2": 1.20,
    "asia-northeast3": 1.20,
    "asia-south1": 1.20,
    "asia-south2": 1.20,
    "asia-southeast2": 1.20,
    # Americas Tier 2
    "northamerica-northeast1": 1.10,
    "northamerica-northeast2": 1.10,
    "southamerica-east1": 1.30,
    "southamerica-west1": 1.30,
    # Australia
    "australia-southeast1": 1.20,
    "australia-southeast2": 1.20,
    # Middle East & Africa
    "me-central1": 1.20,
    "me-central2": 1.20,
    "me-west1": 1.20,
    "africa-south1": 1.25,
}

DEFAULT_REGIONAL_MULTIPLIER = 1.10
DEFAULT_BASE_VCPU_RATE = 0.0450


def parse_vcpus(machine_type: str) -> int:
    """Extract number of guest vCPUs from standard machine type string."""
    if machine_type.endswith(("-micro", "-small", "-medium")):
        return 2
    match = re.search(r"-(\d+)$", machine_type)
    if match:
        return int(match.group(1))
    return 4


def compute_on_demand_price(region: str, machine_type: str, family: str = "") -> float:
    """Compute standard public on-demand hourly price (USD) for a machine type and region."""
    fam = family or machine_type.split("-")[0]
    vcpus = parse_vcpus(machine_type)
    base_rate = FAMILY_BASE_VCPU_RATES.get(fam, DEFAULT_BASE_VCPU_RATE)
    multiplier = REGIONAL_MULTIPLIERS.get(region, DEFAULT_REGIONAL_MULTIPLIER)
    return round(vcpus * base_rate * multiplier, 6)


def generate_on_demand_pricing_rows() -> list[dict[str, Any]]:
    """Generate all on-demand pricing records for every catalog region and machine type."""
    catalog = load_catalog()
    now_iso = datetime.now(UTC).isoformat()
    rows: list[dict[str, Any]] = []

    for reg_target in catalog.regions:
        region = reg_target.region
        for fam_target in catalog.families:
            family = fam_target.family
            for machine_type in fam_target.machine_types:
                vcpus = parse_vcpus(machine_type)
                memory_gb = float(vcpus * 4)
                hourly_price = compute_on_demand_price(region, machine_type, family)

                rows.append({
                    "region": region,
                    "machine_type": machine_type,
                    "family": family,
                    "vcpus": vcpus,
                    "memory_gb": memory_gb,
                    "hourly_price": hourly_price,
                    "currency": "USD",
                    "updated_at": now_iso,
                })

    return rows


def seed_on_demand_pricing_table(
    client: bigquery.Client,
    project: str,
    dataset: str = "mindthespot_raw",
    table_id: str = "on_demand_pricing",
) -> int:
    """Seed or truncate/overwrite the on_demand_pricing table in BigQuery."""
    full_table_id = f"{project}.{dataset}.{table_id}"
    rows = generate_on_demand_pricing_rows()

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=[
            bigquery.SchemaField("region", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("machine_type", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("family", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("vcpus", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("memory_gb", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("hourly_price", "FLOAT", mode="REQUIRED"),
            bigquery.SchemaField("currency", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
        ],
    )

    load_job = client.load_table_from_json(rows, full_table_id, job_config=job_config)
    load_job.result()

    logger.info("Successfully seeded %d on-demand pricing rows into %s", len(rows), full_table_id)
    return len(rows)


def ensure_on_demand_pricing_seeded(
    client: bigquery.Client,
    project: str,
    dataset: str = "mindthespot_raw",
    table_id: str = "on_demand_pricing",
) -> int:
    """Ensure the on_demand_pricing table has records; seed if empty."""
    full_table_id = f"{project}.{dataset}.{table_id}"
    try:
        query = f"SELECT COUNT(1) AS cnt FROM `{full_table_id}`"
        query_job = client.query(query)
        res = query_job.result()
        for row in res:
            if row.cnt > 0:
                logger.info("Table %s already contains %d rows, skipping seed.", full_table_id, row.cnt)
                return int(row.cnt)
    except Exception as e:
        logger.warning("Could not check row count for %s (table might not exist yet): %s", full_table_id, e)

    return seed_on_demand_pricing_table(client, project, dataset, table_id)
