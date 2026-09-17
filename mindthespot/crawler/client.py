"""Async client for GCP Compute advice.capacityHistory API."""

import asyncio
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Any

import httpx

from mindthespot.crawler.models import (
    DailyPreemptionRate,
    PriceIntervalRecord,
)
from mindthespot.crawler.rate_limiter import AsyncTokenBucketRateLimiter

logger = logging.getLogger(__name__)

COMPUTE_BETA_BASE_URL = "https://compute.googleapis.com/compute/beta/projects"


def _extract_preemption_rates_from_entry(entry: dict[str, Any]) -> list[DailyPreemptionRate]:
    """Parse a preemption history entry, expanding multi-day intervals into daily records.

    Google Cloud Compute Engine Capacity History API compresses consecutive days
    with identical preemption rates into a single [startTime, endTime) interval.
    This helper unrolls that interval into individual DailyPreemptionRate objects
    for each calendar date.
    """
    rate_val = float(entry.get("preemptionRate", 0.0))
    if entry.get("date"):
        return [DailyPreemptionRate(date=str(entry["date"])[:10], preemption_rate=rate_val)]

    interval = entry.get("interval")
    if not isinstance(interval, dict) or not interval.get("startTime"):
        return []

    start_str = str(interval["startTime"])[:10]
    end_str = str(interval.get("endTime", ""))[:10]

    try:
        start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
    except ValueError:
        return [DailyPreemptionRate(date=start_str, preemption_rate=rate_val)]

    if end_str:
        try:
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
        except ValueError:
            end_date = start_date + timedelta(days=1)
    else:
        end_date = start_date + timedelta(days=1)

    expanded: list[DailyPreemptionRate] = []
    curr = start_date
    while curr < end_date:
        expanded.append(DailyPreemptionRate(date=curr.isoformat(), preemption_rate=rate_val))
        curr += timedelta(days=1)

    if not expanded:
        expanded.append(DailyPreemptionRate(date=start_str, preemption_rate=rate_val))

    return expanded


class GCPCapacityHistoryClient:
    """Async client with rate limiting and exponential backoff for GCP capacityHistory."""

    def __init__(
        self,
        rate_limiter: AsyncTokenBucketRateLimiter | None = None,
        token_provider: Any = None,
        http_client: httpx.AsyncClient | None = None,
        base_url: str = COMPUTE_BETA_BASE_URL,
        max_retries: int = 3,
        base_backoff_sec: float = 1.0,
    ) -> None:
        self.rate_limiter = rate_limiter or AsyncTokenBucketRateLimiter(rate=15.0, capacity=15.0)
        self.token_provider = token_provider
        self.http_client = http_client
        self._owns_http_client = http_client is None
        self._cached_token: str | None = None
        self._token_expiry: float = 0.0
        self._auth_lock = asyncio.Lock()
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.base_backoff_sec = base_backoff_sec

    async def get_http_client(self) -> httpx.AsyncClient:
        """Get or lazily initialize the shared HTTP/2 client with connection pooling."""
        if self.http_client is None or self.http_client.is_closed:
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=30)
            self.http_client = httpx.AsyncClient(http2=True, timeout=30.0, limits=limits)
            self._owns_http_client = True
        return self.http_client

    async def aclose(self) -> None:
        """Close the underlying HTTP client if owned by this instance."""
        if self._owns_http_client and self.http_client and not self.http_client.is_closed:
            await self.http_client.aclose()

    async def __aenter__(self) -> "GCPCapacityHistoryClient":
        await self.get_http_client()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.aclose()

    async def _get_auth_headers(self) -> dict[str, str]:
        """Obtain authorization headers via token provider or cached Google ADC."""
        if callable(self.token_provider):
            token = self.token_provider()
            if asyncio.iscoroutine(token):
                token = await token
            return {"Authorization": f"Bearer {token}"}
        elif isinstance(self.token_provider, str):
            return {"Authorization": f"Bearer {self.token_provider}"}

        now = time.time()
        if self._cached_token and now < (self._token_expiry - 60):
            return {"Authorization": f"Bearer {self._cached_token}"}

        async with self._auth_lock:
            # Double-check after acquiring lock
            now = time.time()
            if self._cached_token and now < (self._token_expiry - 60):
                return {"Authorization": f"Bearer {self._cached_token}"}

            try:
                import google.auth
                from google.auth.transport.requests import Request

                credentials, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                credentials.refresh(Request())
                self._cached_token = credentials.token
                if credentials.expiry:
                    self._token_expiry = credentials.expiry.timestamp()
                else:
                    self._token_expiry = now + 3500.0
                return {"Authorization": f"Bearer {self._cached_token}"}
            except Exception as e:
                logger.debug("Failed to acquire Google ADC credentials: %s", e)
                return {}

    async def _send_request_with_backoff(
        self,
        url: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Send HTTP POST request under rate limiter with jittered exponential backoff."""
        client = await self.get_http_client()
        headers = await self._get_auth_headers()
        headers["Content-Type"] = "application/json"

        for attempt in range(self.max_retries + 1):
            async with self.rate_limiter:
                try:
                    response = await client.post(url, json=payload, headers=headers)
                except httpx.RequestError as exc:
                    if attempt == self.max_retries:
                        raise
                    logger.warning(
                        "Network error contacting GCP API: %s (attempt %d/%d)",
                        exc,
                        attempt + 1,
                        self.max_retries,
                    )
                    backoff = (self.base_backoff_sec * (2**attempt)) + random.uniform(0.1, 0.5)
                    await asyncio.sleep(backoff)
                    continue

            # Handle rate-limiting (429) or transient service unavailability (503)
            if response.status_code in (429, 503):
                if attempt == self.max_retries:
                    response.raise_for_status()
                backoff = (self.base_backoff_sec * (2**attempt)) + random.uniform(0.1, 0.5)
                logger.warning(
                    "GCP API returned %d; retrying in %.2fs (attempt %d/%d)",
                    response.status_code,
                    backoff,
                    attempt + 1,
                    self.max_retries,
                )
                await asyncio.sleep(backoff)
                continue

            response.raise_for_status()
            return response.json()

        raise RuntimeError("Unexpected exhaustion of retry loop")

    async def fetch_preemption_history(
        self,
        project: str,
        region: str,
        zone: str,
        machine_type: str,
    ) -> list[DailyPreemptionRate]:
        """Fetch 30-day daily spot preemption rate history for a specific zone & machine type."""
        url = f"{self.base_url}/{project}/regions/{region}/advice/capacityHistory"
        payload = {
            "types": ["PREEMPTION"],
            "instanceProperties": {
                "scheduling": {"provisioningModel": "SPOT"},
                "machineType": machine_type,
            },
            "locationPolicy": {
                "location": f"zones/{zone}",
            },
        }

        data = await self._send_request_with_backoff(url, payload)
        rates: list[DailyPreemptionRate] = []

        # Parse direct GCP API format: {"preemptionHistory": [...]}
        raw_preempt_list = data.get("preemptionHistory", [])
        if isinstance(raw_preempt_list, list):
            for entry in raw_preempt_list:
                rates.extend(_extract_preemption_rates_from_entry(entry))

        # Parse nested capacityHistory wrapper format
        for item in data.get("capacityHistory", []):
            if item.get("historyType") == "PREEMPTION":
                preempt_hist = item.get("preemptionHistory", {})
                entries = (
                    preempt_hist.get("dailyPreemptionRates", [])
                    if isinstance(preempt_hist, dict)
                    else preempt_hist
                    if isinstance(preempt_hist, list)
                    else []
                )
                for entry in entries:
                    rates.extend(_extract_preemption_rates_from_entry(entry))

        # Deduplicate and sort chronologically by date
        unique_rates = {r.date: r for r in rates}
        sorted_rates = sorted(unique_rates.values(), key=lambda r: r.date)
        return sorted_rates

    async def fetch_price_history(
        self,
        project: str,
        region: str,
        machine_type: str,
    ) -> list[PriceIntervalRecord]:
        """Fetch 1-year historical spot pricing intervals for a specific region & machine type."""
        url = f"{self.base_url}/{project}/regions/{region}/advice/capacityHistory"
        payload = {
            "types": ["PRICE"],
            "instanceProperties": {
                "scheduling": {"provisioningModel": "SPOT"},
                "machineType": machine_type,
            },
        }

        data = await self._send_request_with_backoff(url, payload)
        intervals: list[PriceIntervalRecord] = []

        # Parse direct GCP API format: {"priceHistory": [...]}
        raw_price_list = data.get("priceHistory", [])
        if isinstance(raw_price_list, list):
            for entry in raw_price_list:
                interval_data = entry.get("interval", {})
                start_t = interval_data.get("startTime")
                end_t = interval_data.get("endTime")
                list_price = entry.get("listPrice", {})
                units = float(list_price.get("units", 0))
                nanos = float(list_price.get("nanos", 0))
                hourly = units + (nanos / 1e9)
                curr = list_price.get("currencyCode", "USD")

                if start_t:
                    intervals.append(
                        PriceIntervalRecord(
                            start_time=start_t,
                            end_time=end_t,
                            hourly_price=round(hourly, 6),
                            currency=curr,
                        )
                    )

        # Parse nested capacityHistory wrapper format
        for item in data.get("capacityHistory", []):
            if item.get("historyType") == "PRICE":
                price_hist = item.get("priceHistory", {})
                entries = (
                    price_hist.get("priceIntervals", [])
                    if isinstance(price_hist, dict)
                    else price_hist
                    if isinstance(price_hist, list)
                    else []
                )
                for entry in entries:
                    interval_data = entry.get("interval", {})
                    start_t = interval_data.get("startTime")
                    end_t = interval_data.get("endTime")
                    list_price = entry.get("listPrice", {})
                    units = float(list_price.get("units", 0))
                    nanos = float(list_price.get("nanos", 0))
                    hourly = units + (nanos / 1e9)
                    curr = list_price.get("currencyCode", "USD")

                    if start_t:
                        intervals.append(
                            PriceIntervalRecord(
                                start_time=start_t,
                                end_time=end_t,
                                hourly_price=round(hourly, 6),
                                currency=curr,
                            )
                        )

        # Sort chronologically by startTime
        intervals.sort(key=lambda i: i.start_time)
        return intervals
