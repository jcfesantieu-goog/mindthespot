"""Asynchronous token-bucket rate limiter for GCP API quota control."""

import asyncio
import time


class AsyncTokenBucketRateLimiter:
    """Async token-bucket rate limiter with concurrency throttling.

    Restricts requests per second to at most `rate` tokens/sec with maximum burst
    `capacity`, while bounding concurrent in-flight requests via `max_concurrency`.
    """

    def __init__(
        self,
        rate: float = 15.0,
        capacity: float = 15.0,
        max_concurrency: int = 10,
    ) -> None:
        if rate <= 0:
            raise ValueError("Rate must be greater than 0")
        if capacity <= 0:
            raise ValueError("Capacity must be greater than 0")
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be greater than 0")

        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill = time.monotonic()
        self.lock = asyncio.Lock()
        self.semaphore = asyncio.Semaphore(max_concurrency)

    def _refill(self) -> None:
        """Refill tokens based on elapsed monotonic time."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_refill = now

    async def acquire(self) -> None:
        """Acquire a rate-limit token, sleeping if necessary until one becomes available."""
        while True:
            async with self.lock:
                self._refill()
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                # Calculate sleep duration until at least 1 token is available
                needed = 1.0 - self.tokens
                sleep_time = needed / self.rate

            await asyncio.sleep(sleep_time)

    async def __aenter__(self):
        """Context manager: acquires both a token and a concurrency semaphore slot."""
        await self.semaphore.acquire()
        try:
            await self.acquire()
        except Exception:
            self.semaphore.release()
            raise
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: releases concurrency semaphore slot."""
        self.semaphore.release()
