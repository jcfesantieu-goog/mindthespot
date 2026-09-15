"""In-memory TTL cache for MindTheSpot API queries."""

from typing import Any

from cachetools import TTLCache

# Default TTL: 15 minutes (900 seconds)
DEFAULT_CACHE_TTL = 900
DEFAULT_CACHE_MAXSIZE = 256

_api_cache = TTLCache(maxsize=DEFAULT_CACHE_MAXSIZE, ttl=DEFAULT_CACHE_TTL)


def get_cached(key: str) -> Any | None:
    """Retrieve value from cache if present and not expired."""
    return _api_cache.get(key)


def set_cached(key: str, value: Any) -> None:
    """Store value into cache with configured TTL."""
    _api_cache[key] = value


def clear_cache() -> None:
    """Clear all cached entries."""
    _api_cache.clear()
