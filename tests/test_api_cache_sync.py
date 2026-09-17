"""Tests for Hybrid Pre-Warm and Background Sync caching architecture."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from mindthespot.api.app import create_app
from mindthespot.api.service import SpotDataService


@pytest.fixture
def test_client():
    """Create test client with fresh SpotDataService instance."""
    app = create_app()
    with TestClient(app) as client:
        yield client


def test_cache_status_synthetic_default(test_client):
    """Verify cache status endpoint returns synthetic status on startup."""
    res = test_client.get("/api/v1/cache/status")
    assert res.status_code == 200
    data = res.json()
    assert "source" in data
    assert "total_pools_cached" in data
    assert data["total_pools_cached"] > 0
    assert "is_warming" in data


def test_cache_refresh_trigger(test_client):
    """Verify cache refresh endpoint initiates asynchronous refresh."""
    res = test_client.post("/api/v1/cache/refresh")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "triggered"
    assert "Background cache synchronization" in data["message"]
    assert "triggered_at" in data


def test_service_warm_cache_mocked_bigquery():
    """Verify warm_cache_from_bigquery populates cache from mocked BigQuery rows."""
    service = SpotDataService()

    # Mock BigQuery Row items
    mock_shift = MagicMock()
    mock_shift.region = "europe-west4"
    mock_shift.zone = "europe-west4-a"
    mock_shift.machine_type = "c4a-standard-4"
    mock_shift.family = "c4a"
    mock_shift.is_watchlist = True
    mock_shift.custom_label = "Production Batch"
    mock_shift.recent_7d_rate = 0.05
    mock_shift.baseline_rate = 0.04
    mock_shift.rate_delta = 0.01
    mock_shift.z_score = 0.8
    mock_shift.hourly_price = 0.022928
    mock_shift.currency = "USD"
    mock_shift.price_hike_detected = False
    mock_shift.severity = "STABLE"

    mock_price = MagicMock()
    mock_price.region = "europe-west4"
    mock_price.machine_type = "c4a-standard-4"
    mock_price.interval_start = datetime(2025, 9, 1, 0, 0, tzinfo=UTC)
    mock_price.interval_end = None
    mock_price.hourly_price = 0.022928
    mock_price.currency = "USD"

    mock_rate = MagicMock()
    mock_rate.region = "europe-west4"
    mock_rate.zone = "europe-west4-a"
    mock_rate.machine_type = "c4a-standard-4"
    mock_rate.telemetry_date = datetime(2026, 9, 16, 0, 0, tzinfo=UTC).date()
    mock_rate.preemption_rate = 0.045

    with patch("google.cloud.bigquery.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        def mock_query(sql):
            mock_job = MagicMock()
            if "v_regime_shifts" in sql:
                mock_job.result.return_value = [mock_shift]
            elif "price_history" in sql:
                mock_job.result.return_value = [mock_price]
            elif "preemption_history" in sql:
                mock_job.result.return_value = [mock_rate]
            else:
                mock_job.result.return_value = []
            return mock_job

        mock_client.query.side_effect = mock_query

        success = service.warm_cache_from_bigquery(project_id="test-project")
        assert success is True

        status = service.get_cache_status()
        assert status["source"] == "bigquery"
        assert status["total_pools_cached"] == 1
        assert status["total_price_intervals"] == 1
        assert status["total_preemption_points"] == 1

        # Check pool lookup
        pool = service.get_pool_history("europe-west4", "europe-west4-a", "c4a-standard-4")
        assert pool is not None
        assert pool.current_hourly_price == 0.022928
        assert pool.is_watchlist is True
        assert pool.custom_label == "Production Batch"
        assert len(pool.intervals) == 1
        assert len(pool.rates) == 1


def test_service_warm_cache_failure_fallback():
    """Verify service gracefully retains cache when BigQuery query fails."""
    service = SpotDataService()
    initial_count = len(service._pool_cache)
    assert initial_count > 0

    with patch("google.cloud.bigquery.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.query.side_effect = RuntimeError("BigQuery connection timeout")

        success = service.warm_cache_from_bigquery(project_id="test-project")
        assert success is False

        # Service still has valid pools from synthetic fallback
        status = service.get_cache_status()
        assert status["source"] == "synthetic"
        assert status["total_pools_cached"] == initial_count
