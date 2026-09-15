"""Tests for MindTheSpot rate limiter, API client, and crawler extractor."""

import time

import httpx
import pytest

from mindthespot.config.models import (
    CatalogConfig,
    MachineFamilyConfig,
    RegionConfig,
)
from mindthespot.crawler.client import GCPCapacityHistoryClient
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
            regions=[RegionConfig(region="europe-west4", zones=["europe-west4-a", "europe-west4-b"])],
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
