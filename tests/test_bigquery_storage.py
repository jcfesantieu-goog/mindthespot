"""Tests for BigQuery schema transformation and storage client."""

from unittest.mock import MagicMock

from google.cloud.exceptions import NotFound

from mindthespot.crawler.models import (
    DailyPreemptionRate,
    PreemptionSnapshotRecord,
    PriceIntervalRecord,
    PriceSnapshotRecord,
)
from mindthespot.storage.bigquery_client import BigQueryStorageClient
from mindthespot.storage.schemas import (
    transform_preemption_records_to_rows,
    transform_price_records_to_rows,
)


def test_transform_preemption_records_to_rows():
    record = PreemptionSnapshotRecord(
        snapshot_date="2026-09-15",
        crawled_at="2026-09-15T08:00:00Z",
        region="europe-west4",
        zone="europe-west4-a",
        machine_type="c4d-standard-8",
        family="c4d",
        rates=[
            DailyPreemptionRate(date="2026-09-14", preemption_rate=0.05),
            DailyPreemptionRate(date="2026-09-15", preemption_rate=0.10),
        ],
        is_watchlist=True,
        custom_label="Nightly Batch",
    )

    rows = transform_preemption_records_to_rows([record])
    assert len(rows) == 2
    assert rows[0]["snapshot_date"] == "2026-09-15"
    assert rows[0]["region"] == "europe-west4"
    assert rows[0]["zone"] == "europe-west4-a"
    assert rows[0]["machine_type"] == "c4d-standard-8"
    assert rows[0]["telemetry_date"] == "2026-09-14"
    assert rows[0]["preemption_rate"] == 0.05
    assert rows[0]["is_watchlist"] is True
    assert rows[0]["custom_label"] == "Nightly Batch"


def test_transform_price_records_to_rows():
    record = PriceSnapshotRecord(
        snapshot_date="2026-09-15",
        crawled_at="2026-09-15T08:00:00Z",
        region="europe-west4",
        machine_type="c4d-standard-8",
        family="c4d",
        intervals=[
            PriceIntervalRecord(
                start_time="2026-01-01T00:00:00Z",
                end_time="2026-06-01T00:00:00Z",
                hourly_price=0.15,
                currency="USD",
            ),
            PriceIntervalRecord(
                start_time="2026-06-01T00:00:00Z",
                end_time=None,
                hourly_price=0.1824,
                currency="USD",
            ),
        ],
        current_hourly_price=0.1824,
    )

    rows = transform_price_records_to_rows([record])
    assert len(rows) == 2
    assert rows[0]["hourly_price"] == 0.15
    assert rows[1]["hourly_price"] == 0.1824
    assert rows[1]["interval_end"] is None


def test_bigquery_storage_client_ensure_tables():
    mock_client = MagicMock()
    # Simulate dataset and tables not existing initially
    mock_client.get_dataset.side_effect = NotFound("Dataset not found")
    mock_client.get_table.side_effect = NotFound("Table not found")

    storage = BigQueryStorageClient(
        project="test-proj",
        dataset="test_raw",
        client=mock_client,
    )

    storage.ensure_dataset_and_tables()

    assert mock_client.create_dataset.call_count == 1
    assert mock_client.create_table.call_count == 3


def test_bigquery_storage_client_insert_rows():
    mock_client = MagicMock()
    mock_job = MagicMock()
    mock_client.load_table_from_json.return_value = mock_job

    storage = BigQueryStorageClient(
        project="test-proj",
        dataset="test_raw",
        client=mock_client,
    )

    rows = [{"test": 123}]
    count = storage.insert_preemption_rows(rows)

    assert count == 1
    mock_client.load_table_from_json.assert_called_once()
    mock_job.result.assert_called_once()


def test_bigquery_storage_client_purge_snapshot():
    mock_client = MagicMock()
    mock_query_job = MagicMock()
    mock_client.query.return_value = mock_query_job

    storage = BigQueryStorageClient(
        project="test-proj",
        dataset="test_raw",
        client=mock_client,
    )

    storage.purge_snapshot("2026-09-17", region="europe-west1")

    # Should execute DELETE for both preemption_history and price_history
    assert mock_client.query.call_count == 2
    assert mock_query_job.result.call_count == 2

    # Verify query contains DELETE and parameters
    first_call_args = mock_client.query.call_args_list[0][0][0]
    assert "DELETE FROM `test-proj.test_raw.preemption_history`" in first_call_args
    assert "WHERE snapshot_date = @snapshot_date AND region = @region" in first_call_args

    second_call_args = mock_client.query.call_args_list[1][0][0]
    assert "DELETE FROM `test-proj.test_raw.price_history`" in second_call_args


def test_bigquery_storage_client_seed_pricing():
    mock_client = MagicMock()
    mock_job = MagicMock()
    mock_client.load_table_from_json.return_value = mock_job

    storage = BigQueryStorageClient(
        project="test-proj",
        dataset="test_raw",
        client=mock_client,
    )

    count = storage.seed_on_demand_pricing()
    assert count > 0
    mock_client.load_table_from_json.assert_called_once()
    mock_job.result.assert_called_once()

