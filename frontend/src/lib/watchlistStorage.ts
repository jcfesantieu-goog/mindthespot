import { WatchlistEntry, WatchlistSyncResponse } from "../types";
import { fetchWatchlistState, syncWatchlist } from "./api";

export interface LocalWatchlistState {
  entries: WatchlistEntry[];
  starred_pools: string[];
  custom_labels: Record<string, string>;
}

export function getWatchlistStorageKey(email?: string): string {
  return `mindthespot_watchlist_${email || "anonymous"}`;
}

/**
 * Load user watchlist state from LocalStorage.
 * Handles backward compatibility with legacy string array format.
 */
export function loadLocalWatchlist(email?: string): LocalWatchlistState {
  const key = getWatchlistStorageKey(email);
  try {
    const raw = localStorage.getItem(key);
    if (!raw) {
      return { entries: [], starred_pools: [], custom_labels: {} };
    }
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      // Legacy format: array of pool keys
      return {
        entries: [],
        starred_pools: parsed,
        custom_labels: {},
      };
    }
    return {
      entries: Array.isArray(parsed.entries) ? parsed.entries : [],
      starred_pools: Array.isArray(parsed.starred_pools) ? parsed.starred_pools : [],
      custom_labels: parsed.custom_labels && typeof parsed.custom_labels === "object" ? parsed.custom_labels : {},
    };
  } catch (err) {
    console.warn("Failed to load local watchlist from localStorage:", err);
    return { entries: [], starred_pools: [], custom_labels: {} };
  }
}

/**
 * Persist user watchlist state to LocalStorage.
 */
export function saveLocalWatchlist(state: LocalWatchlistState, email?: string): void {
  const key = getWatchlistStorageKey(email);
  try {
    localStorage.setItem(key, JSON.stringify(state));
  } catch (err) {
    console.warn("Failed to save local watchlist to localStorage:", err);
  }
}

/**
 * Hydrate and synchronize watchlist bidirectionally between LocalStorage and BigQuery via backend API.
 * 1. Reads local cache.
 * 2. Syncs with backend API (server merges with BigQuery state).
 * 3. Saves merged state into local storage and returns it.
 */
export async function hydrateAndSyncWatchlist(email?: string): Promise<LocalWatchlistState> {
  const local = loadLocalWatchlist(email);

  try {
    // If local has entries or starred pools, send sync payload to merge with server
    let serverState: WatchlistSyncResponse;
    if (local.entries.length > 0 || local.starred_pools.length > 0) {
      serverState = await syncWatchlist({
        entries: local.entries,
        starred_pools: local.starred_pools,
        custom_labels: local.custom_labels,
      });
    } else {
      serverState = await fetchWatchlistState();
    }

    const mergedState: LocalWatchlistState = {
      entries: serverState.entries || [],
      starred_pools: serverState.starred_pools || [],
      custom_labels: serverState.custom_labels || {},
    };

    saveLocalWatchlist(mergedState, email);
    return mergedState;
  } catch (err) {
    console.warn("Could not sync watchlist with server, falling back to local storage:", err);
    return local;
  }
}

/**
 * Update a starred pool locally and return new state.
 */
export function updateLocalStarredPool(
  poolKey: string,
  isStarred: boolean,
  customLabel?: string | null,
  email?: string
): LocalWatchlistState {
  const state = loadLocalWatchlist(email);
  if (isStarred) {
    if (!state.starred_pools.includes(poolKey)) {
      state.starred_pools.push(poolKey);
    }
    if (customLabel) {
      state.custom_labels[poolKey] = customLabel;
    }
  } else {
    state.starred_pools = state.starred_pools.filter((k) => k !== poolKey);
    delete state.custom_labels[poolKey];
  }
  saveLocalWatchlist(state, email);
  return state;
}

/**
 * Remove a watchlist target entry from local storage.
 */
export function removeLocalWatchlistTarget(
  target: WatchlistEntry,
  email?: string
): LocalWatchlistState {
  const state = loadLocalWatchlist(email);
  state.entries = state.entries.filter(
    (e) => !(e.region === target.region && (e.name || "") === (target.name || ""))
  );

  // Also remove corresponding starred pools
  for (const mt of target.machine_types) {
    const zones = target.zones && target.zones.length > 0 ? target.zones : [`${target.region}-a`];
    for (const z of zones) {
      const key = `${target.region}/${z}/${mt}`;
      state.starred_pools = state.starred_pools.filter((k) => k !== key);
      delete state.custom_labels[key];
    }
  }

  saveLocalWatchlist(state, email);
  return state;
}
