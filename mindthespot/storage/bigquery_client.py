"""BigQuery client for partitioned table creation and batch ingestion."""

import logging
from typing import Any

from google.cloud import bigquery
from google.cloud.exceptions import NotFound

from mindthespot.storage.schemas import (
    PREEMPTION_TABLE_SCHEMA,
    PRICE_TABLE_SCHEMA,
)

logger = logging.getLogger(__name__)


class BigQueryStorageClient:
    """Client for managing BigQuery datasets, tables, and partitioned batch loading."""

    def __init__(
        self,
        project: str,
        dataset: str = "mindthespot_raw",
        client: bigquery.Client | None = None,
    ) -> None:
        self.project = project
        self.dataset = dataset
        self._client = client

    @property
    def client(self) -> bigquery.Client:
        """Lazy load or return initialized BigQuery client."""
        if self._client is None:
            self._client = bigquery.Client(project=self.project)
        return self._client

    def ensure_dataset_and_tables(self) -> None:
        """Ensure target dataset and partitioned tables exist."""
        dataset_ref = bigquery.DatasetReference(self.project, self.dataset)
        try:
            self.client.get_dataset(dataset_ref)
        except NotFound:
            ds = bigquery.Dataset(dataset_ref)
            ds.description = "MindTheSpot raw spot VM preemption and pricing telemetry"
            self.client.create_dataset(ds, exists_ok=True)
            logger.info("Created BigQuery dataset %s.%s", self.project, self.dataset)

        # 1. Ensure Preemption Table
        preempt_table_id = f"{self.project}.{self.dataset}.preemption_history"
        try:
            self.client.get_table(preempt_table_id)
        except NotFound:
            table = bigquery.Table(preempt_table_id, schema=PREEMPTION_TABLE_SCHEMA)
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="snapshot_date",
            )
            table.clustering_fields = ["region", "zone", "machine_type"]
            self.client.create_table(table, exists_ok=True)
            logger.info("Created BigQuery table %s", preempt_table_id)

        # 2. Ensure Price Table
        price_table_id = f"{self.project}.{self.dataset}.price_history"
        try:
            self.client.get_table(price_table_id)
        except NotFound:
            table = bigquery.Table(price_table_id, schema=PRICE_TABLE_SCHEMA)
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="snapshot_date",
            )
            table.clustering_fields = ["region", "machine_type"]
            self.client.create_table(table, exists_ok=True)
            logger.info("Created BigQuery table %s", price_table_id)

    def load_rows_into_table(
        self,
        table_name: str,
        rows: list[dict[str, Any]],
        schema: list[bigquery.SchemaField],
    ) -> int:
        """Load JSON rows into target BigQuery table via batch load job."""
        if not rows:
            return 0

        table_id = f"{self.project}.{self.dataset}.{table_name}"
        job_config = bigquery.LoadJobConfig(
            schema=schema,
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )

        load_job = self.client.load_table_from_json(
            rows,
            table_id,
            job_config=job_config,
        )
        load_job.result()  # Wait for job completion
        logger.info("Loaded %d rows into %s", len(rows), table_id)
        return len(rows)

    def insert_preemption_rows(self, rows: list[dict[str, Any]]) -> int:
        """Insert transformed preemption rows into preemption_history."""
        return self.load_rows_into_table(
            "preemption_history",
            rows,
            PREEMPTION_TABLE_SCHEMA,
        )

    def insert_price_rows(self, rows: list[dict[str, Any]]) -> int:
        """Insert transformed price rows into price_history."""
        return self.load_rows_into_table(
            "price_history",
            rows,
            PRICE_TABLE_SCHEMA,
        )

    def purge_snapshot(self, snapshot_date: str, region: str | None = None) -> None:
        """Purge existing records for the given snapshot_date to ensure idempotent re-runs."""
        where_clause = "WHERE snapshot_date = @snapshot_date"
        params = [bigquery.ScalarQueryParameter("snapshot_date", "DATE", snapshot_date)]

        if region:
            where_clause += " AND region = @region"
            params.append(bigquery.ScalarQueryParameter("region", "STRING", region))

        for table_name in ("preemption_history", "price_history"):
            query = f"DELETE FROM `{self.project}.{self.dataset}.{table_name}` {where_clause}"
            try:
                job_config = bigquery.QueryJobConfig(query_parameters=params)
                self.client.query(query, job_config=job_config).result()
                logger.info(
                    "Purged existing records from %s for snapshot %s (region=%s)",
                    table_name,
                    snapshot_date,
                    region or "ALL",
                )
            except Exception as e:
                logger.warning(
                    "Could not purge snapshot %s from %s: %s",
                    snapshot_date,
                    table_name,
                    e,
                )
