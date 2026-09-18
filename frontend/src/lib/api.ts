import {
  AnomalyItem,
  PivotRecommendationResponse,
  PoolHistory,
  PoolSummary,
  Severity,
  WatchlistEntry,
} from "../types";

const BASE_URL = "/api";

export async function fetchAnomalies(params?: {
  severity?: Severity;
  region?: string;
  watchlistOnly?: boolean;
  priceFilter?: "HIKE" | "DROP";
}): Promise<AnomalyItem[]> {
  const query = new URLSearchParams();
  if (params?.severity) query.set("severity", params.severity);
  if (params?.region) query.set("region", params.region);
  if (params?.watchlistOnly) query.set("watchlist_only", "true");
  if (params?.priceFilter) query.set("price_filter", params.priceFilter);

  const res = await fetch(`${BASE_URL}/v1/anomalies?${query.toString()}`);
  if (!res.ok) throw new Error(`Failed to fetch anomalies: ${res.statusText}`);
  return res.json();
}

export async function fetchPools(params?: {
  region?: string;
  family?: string;
  watchlistOnly?: boolean;
  search?: string;
}): Promise<PoolSummary[]> {
  const query = new URLSearchParams();
  if (params?.region) query.set("region", params.region);
  if (params?.family) query.set("family", params.family);
  if (params?.watchlistOnly) query.set("watchlist_only", "true");
  if (params?.search) query.set("search", params.search);

  const res = await fetch(`${BASE_URL}/v1/pools?${query.toString()}`);
  if (!res.ok) throw new Error(`Failed to fetch pools: ${res.statusText}`);
  return res.json();
}

export async function fetchPoolHistory(
  region: string,
  zone: string,
  machineType: string
): Promise<PoolHistory> {
  const res = await fetch(
    `${BASE_URL}/v1/pools/${encodeURIComponent(region)}/${encodeURIComponent(
      zone
    )}/${encodeURIComponent(machineType)}/history`
  );
  if (!res.ok) throw new Error(`Failed to fetch pool history: ${res.statusText}`);
  return res.json();
}

export async function fetchPivots(
  region: string,
  zone: string,
  machineType: string
): Promise<PivotRecommendationResponse> {
  const res = await fetch(
    `${BASE_URL}/v1/pivots/${encodeURIComponent(region)}/${encodeURIComponent(
      zone
    )}/${encodeURIComponent(machineType)}`
  );
  if (!res.ok) throw new Error(`Failed to fetch pivots: ${res.statusText}`);
  return res.json();
}

export async function fetchWatchlist(): Promise<WatchlistEntry[]> {
  const res = await fetch(`${BASE_URL}/v1/watchlist`);
  if (!res.ok) throw new Error(`Failed to fetch watchlist: ${res.statusText}`);
  return res.json();
}

export async function addWatchlistTarget(entry: {
  name?: string;
  region: string;
  zones?: string[];
  machine_types: string[];
}): Promise<void> {
  const res = await fetch(`${BASE_URL}/v1/watchlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry),
  });
  if (!res.ok) throw new Error(`Failed to add watchlist: ${res.statusText}`);
}

export async function toggleWatchlistPool(payload: {
  region: string;
  zone: string;
  machine_type: string;
  is_watchlist: boolean;
  custom_label?: string | null;
}): Promise<void> {
  const res = await fetch(`${BASE_URL}/v1/watchlist/toggle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Failed to toggle watchlist pool: ${res.statusText}`);
}

export async function deleteWatchlistPool(
  region: string,
  zone: string,
  machine_type: string
): Promise<void> {
  const res = await fetch(
    `${BASE_URL}/v1/watchlist/${encodeURIComponent(region)}/${encodeURIComponent(
      zone
    )}/${encodeURIComponent(machine_type)}`,
    {
      method: "DELETE",
    }
  );
  if (!res.ok) throw new Error(`Failed to delete watchlist pool: ${res.statusText}`);
}

export async function deleteWatchlistTarget(
  region: string,
  name?: string | null
): Promise<void> {
  const params = new URLSearchParams({ region });
  if (name) params.set("name", name);
  const res = await fetch(`${BASE_URL}/v1/watchlist?${params.toString()}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Failed to delete watchlist target: ${res.statusText}`);
}

export interface UserContextResponse {
  email: string;
  user_id?: string | null;
  is_authenticated: boolean;
}

export async function fetchCurrentUser(): Promise<UserContextResponse> {
  try {
    const res = await fetch(`${BASE_URL}/v1/auth/me`);
    if (!res.ok) return { email: "dev@mindthespot.internal", is_authenticated: false };
    return res.json();
  } catch {
    return { email: "dev@mindthespot.internal", is_authenticated: false };
  }
}

export interface CacheStatusResponse {
  source: "bigquery" | "synthetic" | string;
  last_synced_at: string | null;
  total_pools_cached: number;
  total_price_intervals: number;
  total_preemption_points: number;
  is_warming: boolean;
}

export interface CacheRefreshResponse {
  status: string;
  message: string;
  triggered_at: string;
}

export async function fetchCacheStatus(): Promise<CacheStatusResponse> {
  const res = await fetch(`${BASE_URL}/v1/cache/status`);
  if (!res.ok) throw new Error(`Failed to fetch cache status: ${res.statusText}`);
  return res.json();
}

export async function triggerCacheRefresh(): Promise<CacheRefreshResponse> {
  const res = await fetch(`${BASE_URL}/v1/cache/refresh`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Failed to trigger cache refresh: ${res.statusText}`);
  return res.json();
}


