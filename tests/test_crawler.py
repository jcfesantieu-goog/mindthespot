"""Tests for MindTheSpot rate limiter, API client, and crawler extractor."""

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from mindthespot.config.models import (
    CatalogConfig,
    MachineFamilyConfig,
    RegionConfig,
)
from mindthespot.crawler.client import (
    GCPCapacityHistoryClient,
    _extract_preemption_rates_from_entry,
)
from mindthespot.crawler.extractor import CrawlEngine
from mindthespot.crawler.rate_limiter import AsyncTokenBucketRateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_throttles_acquisitions():
    # Rate of 10 tokens/sec, initial capacity 2 tokens
    limiter = AsyncTokenBucketRateLimiter(rate=10.0, capacity=2.0)

    start = time.monotonic()
    # Acquire 5 tokens: 2 are immediate, 3 require 3/10 = 0.3s
    for _ in range(5):
        await limiter.acquire()
    elapsed = time.monotonic() - start

    assert elapsed >= 0.25


@pytest.mark.asyncio
async def test_rate_limiter_context_manager():
    limiter = AsyncTokenBucketRateLimiter(rate=100.0, capacity=10.0, max_concurrency=2)
    async with limiter:
        assert limiter.tokens < 10.0


@pytest.mark.asyncio
async def test_fetch_preemption_history(mock_preemption_api_response):
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "capacityHistory" in request.url.path
        return httpx.Response(200, json=mock_preemption_api_response)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GCPCapacityHistoryClient(
            token_provider="fake-token",
            http_client=http_client,
        )

        rates = await client.fetch_preemption_history(
            project="test-proj",
            region="europe-west4",
            zone="europe-west4-a",
            machine_type="c4d-standard-8",
        )

        assert len(rates) == 7
        assert rates[0].date == "2026-09-01"
        assert rates[0].preemption_rate == 0.05
        assert rates[-1].date == "2026-09-07"
        assert rates[-1].preemption_rate == 0.35


@pytest.mark.asyncio
async def test_fetch_price_history(mock_price_api_response):
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_price_api_response)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GCPCapacityHistoryClient(
            token_provider="fake-token",
            http_client=http_client,
        )

        intervals = await client.fetch_price_history(
            project="test-proj",
            region="europe-west4",
            machine_type="c4d-standard-8",
        )

        assert len(intervals) == 2
        assert intervals[0].hourly_price == 0.15
        assert intervals[1].hourly_price == 0.1824
        assert intervals[1].end_time is None


@pytest.mark.asyncio
async def test_client_retries_on_429(mock_preemption_api_response):
    attempts = 0

    async def mock_flaky_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, json={"error": "Rate limit exceeded"})
        return httpx.Response(200, json=mock_preemption_api_response)

    transport = httpx.MockTransport(mock_flaky_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GCPCapacityHistoryClient(
            token_provider="fake-token",
            http_client=http_client,
            max_retries=2,
            base_backoff_sec=0.01,
        )

        rates = await client.fetch_preemption_history(
            project="test-proj",
            region="europe-west4",
            zone="europe-west4-a",
            machine_type="c4d-standard-8",
        )

        assert attempts == 2
        assert len(rates) == 7


@pytest.mark.asyncio
async def test_crawl_engine_run(mock_preemption_api_response, mock_price_api_response):
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        content = request.read().decode("utf-8")
        if "PREEMPTION" in content:
            return httpx.Response(200, json=mock_preemption_api_response)
        return httpx.Response(200, json=mock_price_api_response)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GCPCapacityHistoryClient(
            token_provider="fake-token",
            http_client=http_client,
            base_backoff_sec=0.01,
        )

        catalog = CatalogConfig(
            regions=[
                RegionConfig(region="europe-west4", zones=["europe-west4-a", "europe-west4-b"])
            ],
            families=[
                MachineFamilyConfig(
                    family="c4d",
                    machine_types=["c4d-standard-8"],
                    equivalent_families=["c3d"],
                )
            ],
        )

        engine = CrawlEngine(client=client, catalog=catalog, project="test-proj")
        preempt_records, price_records, summary = await engine.run()

        # 2 zones * 1 machine = 2 preemption records
        assert len(preempt_records) == 2
        # 1 region * 1 machine = 1 price record
        assert len(price_records) == 1
        assert summary.successful_preemption_queries == 2
        assert summary.successful_price_queries == 1
        assert summary.failed_queries == 0

        first_preempt = preempt_records[0]
        assert first_preempt.latest_rate == 0.35
        assert first_preempt.avg_7d_rate > 0.10

        first_price = price_records[0]
        assert first_price.current_hourly_price == 0.1824


@pytest.mark.asyncio
async def test_client_shared_session_and_token_cache(mock_preemption_api_response):
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_preemption_api_response)

    transport = httpx.MockTransport(mock_handler)
    async with GCPCapacityHistoryClient(
        token_provider="fake-token",
        http_client=httpx.AsyncClient(transport=transport),
    ) as client:
        # Verify shared client lifecycle
        http_c1 = await client.get_http_client()
        http_c2 = await client.get_http_client()
        assert http_c1 is http_c2

        # Verify token caching
        client._cached_token = "cached-jwt-123"
        client._token_expiry = time.time() + 1800
        client.token_provider = None  # Force reliance on cached token
        headers = await client._get_auth_headers()
        assert headers == {"Authorization": "Bearer cached-jwt-123"}


@pytest.mark.asyncio
async def test_crawl_engine_streaming_callback(
    mock_preemption_api_response, mock_price_api_response
):
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        content = request.read().decode("utf-8")
        if "PREEMPTION" in content:
            return httpx.Response(200, json=mock_preemption_api_response)
        return httpx.Response(200, json=mock_price_api_response)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GCPCapacityHistoryClient(
            token_provider="fake-token",
            http_client=http_client,
            base_backoff_sec=0.01,
        )

        catalog = CatalogConfig(
            regions=[
                RegionConfig(region="europe-west4", zones=["europe-west4-a", "europe-west4-b"])
            ],
            families=[
                MachineFamilyConfig(
                    family="c4d",
                    machine_types=["c4d-standard-8"],
                    equivalent_families=["c3d"],
                )
            ],
        )

        streamed_batches: list[tuple[str, int, int]] = []

        async def mock_stream_sink(reg, p_recs, pr_recs):
            streamed_batches.append((reg, len(p_recs), len(pr_recs)))

        engine = CrawlEngine(client=client, catalog=catalog, project="test-proj")
        preempt_records, price_records, summary = await engine.run(
            on_region_complete=mock_stream_sink,
        )

        # In streaming mode, in-memory return lists are empty to save RAM
        assert len(preempt_records) == 0
        assert len(price_records) == 0

        # But callback received the records
        assert len(streamed_batches) == 1
        assert streamed_batches[0] == ("europe-west4", 2, 1)

        # Summary tracks full metrics
        assert summary.successful_preemption_queries == 2
        assert summary.successful_price_queries == 1
        assert summary.total_preemption_pools == 2
        assert summary.total_price_pools == 1


def test_extract_preemption_rates_multi_day_interval():
    # 14-day interval like c4a-standard-16 from 09-03 to 09-17
    entry = {
        "interval": {
            "startTime": "2026-09-03T07:00:00Z",
            "endTime": "2026-09-17T07:00:00Z",
        },
        "preemptionRate": 0.0,
    }
    rates = _extract_preemption_rates_from_entry(entry)
    assert len(rates) == 14
    assert rates[0].date == "2026-09-03"
    assert rates[0].preemption_rate == 0.0
    assert rates[-1].date == "2026-09-16"
    assert rates[-1].preemption_rate == 0.0

    # Single-day date entry
    date_entry = {"date": "2026-09-01", "preemptionRate": 0.15}
    single_rates = _extract_preemption_rates_from_entry(date_entry)
    assert len(single_rates) == 1
    assert single_rates[0].date == "2026-09-01"
    assert single_rates[0].preemption_rate == 0.15

    # Missing endTime defaults to 1 day
    no_end_entry = {
        "interval": {"startTime": "2026-09-02T07:00:00Z"},
        "preemptionRate": 0.5,
    }
    no_end_rates = _extract_preemption_rates_from_entry(no_end_entry)
    assert len(no_end_rates) == 1
    assert no_end_rates[0].date == "2026-09-02"
    assert no_end_rates[0].preemption_rate == 0.5


@pytest.mark.asyncio
async def test_fetch_preemption_history_expands_compressed_intervals():
    compressed_api_response = {
        "preemptionHistory": [
            {
                "interval": {
                    "startTime": "2026-09-01T07:00:00Z",
                    "endTime": "2026-09-05T07:00:00Z",
                },
                "preemptionRate": 0.02,
            },
            {
                "interval": {
                    "startTime": "2026-09-05T07:00:00Z",
                    "endTime": "2026-09-08T07:00:00Z",
                },
                "preemptionRate": 0.10,
            },
        ]
    }

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=compressed_api_response)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GCPCapacityHistoryClient(token_provider="fake-token", http_client=http_client)
        rates = await client.fetch_preemption_history(
            project="test-proj",
            region="europe-west1",
            zone="europe-west1-d",
            machine_type="c4a-standard-16",
        )

        # 4 days (01, 02, 03, 04) + 3 days (05, 06, 07) = 7 consecutive daily points
        assert len(rates) == 7
        assert [r.date for r in rates] == [
            "2026-09-01",
            "2026-09-02",
            "2026-09-03",
            "2026-09-04",
            "2026-09-05",
            "2026-09-06",
            "2026-09-07",
        ]
        assert [r.preemption_rate for r in rates] == [
            0.02,
            0.02,
            0.02,
            0.02,
            0.10,
            0.10,
            0.10,
        ]


@pytest.mark.asyncio
async def test_client_retries_on_network_error(mock_preemption_api_response):
    attempts = 0

    async def mock_network_error_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("Network unreachable", request=request)
        return httpx.Response(200, json=mock_preemption_api_response)

    transport = httpx.MockTransport(mock_network_error_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GCPCapacityHistoryClient(
            token_provider="fake-token",
            http_client=http_client,
            max_retries=2,
            base_backoff_sec=0.01,
        )

        rates = await client.fetch_preemption_history(
            project="test-proj",
            region="europe-west4",
            zone="europe-west4-a",
            machine_type="c4d-standard-8",
        )
        assert attempts == 2
        assert len(rates) == 7


@pytest.mark.asyncio
async def test_client_adc_auth_token_resolution():
    with patch("google.auth.default") as mock_auth_default:
        mock_creds = MagicMock()
        mock_creds.token = "adc-mocked-bearer-token"
        mock_creds.expiry = None
        mock_auth_default.return_value = (mock_creds, "mock-project")

        client = GCPCapacityHistoryClient()
        headers = await client._get_auth_headers()
        assert headers == {"Authorization": "Bearer adc-mocked-bearer-token"}

