import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  Compass,
  Star,
  RefreshCw,
  Radio,
  ExternalLink,
  UserCheck,
  Database,
} from "lucide-react";
import { AnomalyItem, PivotCandidate, PoolSummary, WatchlistEntry } from "./types";
import {
  fetchAnomalies,
  fetchCurrentUser,
  fetchPivots,
  fetchPools,
  fetchWatchlist,
  fetchCacheStatus,
  triggerCacheRefresh,
  CacheStatusResponse,
  toggleWatchlistPool,
  deleteWatchlistPool,
  deleteWatchlistTarget,
  UserContextResponse,
} from "./lib/api";
import { SituationRoom } from "./components/SituationRoom";
import { PoolExplorer } from "./components/PoolExplorer";
import { WatchlistManager } from "./components/WatchlistManager";
import { InspectorModal } from "./components/InspectorModal";
import { PivotModal } from "./components/PivotModal";
import { cn } from "./lib/utils";

type TabType = "situation-room" | "explorer" | "watchlist";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>("situation-room");
  const [anomalies, setAnomalies] = useState<AnomalyItem[]>([]);
  const [pools, setPools] = useState<PoolSummary[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [userContext, setUserContext] = useState<UserContextResponse | null>(null);
  const [cacheStatus, setCacheStatus] = useState<CacheStatusResponse | null>(null);
  const [showCacheDetails, setShowCacheDetails] = useState<boolean>(false);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isForceRefreshing, setIsForceRefreshing] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState<string>("");

  // Inspector modal state
  const [inspectTarget, setInspectTarget] = useState<{
    region: string;
    zone: string;
    machineType: string;
  } | null>(null);

  // Pivot modal state
  const [pivotTarget, setPivotTarget] = useState<{
    poolKey: string;
    pivots: PivotCandidate[];
  } | null>(null);

  const getStorageKey = (email?: string) => `mindthespot_watchlist_${email || "anonymous"}`;

  const loadAllData = async () => {
    setIsRefreshing(true);
    try {
      const [anomRes, poolRes, watchRes, userRes, cacheRes] = await Promise.allSettled([
        fetchAnomalies(),
        fetchPools(),
        fetchWatchlist(),
        fetchCurrentUser(),
        fetchCacheStatus(),
      ]);

      const email = userRes.status === "fulfilled" ? userRes.value.email : undefined;
      const storageKey = getStorageKey(email);
      let localStarred: string[] = [];
      try {
        const raw = localStorage.getItem(storageKey);
        if (raw) localStarred = JSON.parse(raw);
      } catch (e) {
        console.warn("Failed to parse local watchlist cache", e);
      }

      if (userRes.status === "fulfilled") setUserContext(userRes.value);
      if (watchRes.status === "fulfilled") setWatchlist(watchRes.value);
      if (cacheRes.status === "fulfilled") setCacheStatus(cacheRes.value);

      if (poolRes.status === "fulfilled") {
        const enrichedPools = poolRes.value.map((p) => ({
          ...p,
          is_watchlist: p.is_watchlist || localStarred.includes(p.pool_key),
        }));
        setPools(enrichedPools);
      }

      if (anomRes.status === "fulfilled") {
        const enrichedAnomalies = anomRes.value.map((a) => ({
          ...a,
          is_watchlist: a.is_watchlist || localStarred.includes(a.pool_key),
        }));
        setAnomalies(enrichedAnomalies);
      }

      setLastRefreshed(new Date().toLocaleTimeString());
    } catch (err) {
      console.error("Error loading MindTheSpot data:", err);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  };

  const handleForceRefresh = async () => {
    setIsForceRefreshing(true);
    try {
      await triggerCacheRefresh();
      // Wait briefly for pre-warm initiation then reload
      setTimeout(async () => {
        await loadAllData();
        setIsForceRefreshing(false);
      }, 1500);
    } catch (err) {
      console.error("Failed to trigger cache refresh:", err);
      await loadAllData();
      setIsForceRefreshing(false);
    }
  };

  const handleToggleWatchlist = async (pool: PoolSummary) => {
    const nextState = !pool.is_watchlist;

    // 1. Optimistic UI update
    setPools((prev) =>
      prev.map((p) => (p.pool_key === pool.pool_key ? { ...p, is_watchlist: nextState } : p))
    );
    setAnomalies((prev) =>
      prev.map((a) => (a.pool_key === pool.pool_key ? { ...a, is_watchlist: nextState } : a))
    );

    // 2. Client-side LocalStorage Persistence
    try {
      const storageKey = getStorageKey(userContext?.email);
      const raw = localStorage.getItem(storageKey);
      let starred: string[] = raw ? JSON.parse(raw) : [];
      if (nextState) {
        if (!starred.includes(pool.pool_key)) starred.push(pool.pool_key);
      } else {
        starred = starred.filter((k) => k !== pool.pool_key);
      }
      localStorage.setItem(storageKey, JSON.stringify(starred));
    } catch (e) {
      console.warn("Error updating localStorage watchlist", e);
    }

    // 3. Backend Persistence
    try {
      await toggleWatchlistPool({
        region: pool.region,
        zone: pool.zone,
        machine_type: pool.machine_type,
        is_watchlist: nextState,
        custom_label: pool.custom_label,
      });
    } catch (err) {
      console.error("Failed to sync watchlist to server:", err);
    }
  };

  const handleRemoveWatchlistTarget = async (entry: WatchlistEntry) => {
    try {
      const storageKey = getStorageKey(userContext?.email);
      const raw = localStorage.getItem(storageKey);
      let starred: string[] = raw ? JSON.parse(raw) : [];

      for (const mt of entry.machine_types) {
        for (const zone of entry.zones.length > 0 ? entry.zones : [`${entry.region}-a`]) {
          const key = `${entry.region}/${zone}/${mt}`;
          starred = starred.filter((k) => k !== key);
        }
      }
      localStorage.setItem(storageKey, JSON.stringify(starred));

      try {
        await deleteWatchlistTarget(entry.region, entry.name);
      } catch (e) {
        // Fallback to pool-by-pool delete
        for (const mt of entry.machine_types) {
          for (const zone of entry.zones.length > 0 ? entry.zones : [`${entry.region}-a`]) {
            try {
              await deleteWatchlistPool(entry.region, zone, mt);
            } catch {}
          }
        }
      }
      await loadAllData();
    } catch (err) {
      console.error("Failed to remove watchlist target:", err);
    }
  };

  useEffect(() => {
    loadAllData();
    const interval = setInterval(loadAllData, 60000); // 60s auto polling
    return () => clearInterval(interval);
  }, []);

  const handleOpenPivots = async (
    region: string,
    zone: string,
    machineType: string
  ) => {
    try {
      const res = await fetchPivots(region, zone, machineType);
      setPivotTarget({
        poolKey: res.pool_key,
        pivots: res.pivots,
      });
    } catch (err) {
      console.error("Failed to load pivots:", err);
    }
  };

  const criticalShiftsCount = anomalies.filter(
    (a) => a.severity === "CRITICAL"
  ).length;

  return (
    <div className="min-h-screen bg-[#0b0f19] text-slate-100 flex flex-col">
      {/* Top Navigation Bar */}
      <header className="border-b border-slate-800/80 bg-slate-950/70 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          {/* Logo & Subtitle */}
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
              <Radio className="w-5 h-5 text-white animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-extrabold font-mono tracking-tight text-white">
                  MindTheSpot
                </h1>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                  Expert Lens v0.1
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-mono hidden sm:block">
                Regime Shift Warning & Fallback Pivot Engine
              </p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center gap-1 bg-slate-900/90 p-1 rounded-xl border border-slate-800 text-xs font-mono">
            <button
              onClick={() => setActiveTab("situation-room")}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all font-semibold relative",
                activeTab === "situation-room"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              )}
            >
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
              <span>Situation Room</span>
              {criticalShiftsCount > 0 && (
                <span className="w-2 h-2 rounded-full bg-red-500 animate-ping absolute -top-0.5 -right-0.5" />
              )}
            </button>

            <button
              onClick={() => setActiveTab("explorer")}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all font-semibold",
                activeTab === "explorer"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              )}
            >
              <Compass className="w-3.5 h-3.5" />
              <span>Pool Explorer</span>
            </button>

            <button
              onClick={() => setActiveTab("watchlist")}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all font-semibold",
                activeTab === "watchlist"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              )}
            >
              <Star className="w-3.5 h-3.5 text-amber-400" />
              <span>Watchlist</span>
            </button>
          </nav>

          {/* Status & User & Refresh */}
          <div className="flex items-center gap-3">
            {userContext && (
              <div
                className={cn(
                  "hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-mono",
                  userContext.is_authenticated
                    ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
                    : "bg-slate-900/80 text-slate-400 border-slate-800"
                )}
                title={userContext.is_authenticated ? "Authenticated via Cloud IAP" : "Local Development Mode"}
              >
                <UserCheck className={cn("w-3.5 h-3.5", userContext.is_authenticated ? "text-emerald-400" : "text-slate-500")} />
                <span className="truncate max-w-[150px]">{userContext.email}</span>
              </div>
            )}

            {/* Cache Provenance Badge with Popover */}
            <div className="relative">
              <button
                onClick={() => setShowCacheDetails(!showCacheDetails)}
                className={cn(
                  "hidden sm:flex items-center gap-2 px-2.5 py-1 rounded-lg border text-xs font-mono transition-all cursor-pointer",
                  cacheStatus?.is_warming
                    ? "bg-amber-500/10 text-amber-300 border-amber-500/30"
                    : cacheStatus?.source === "bigquery"
                    ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/20"
                    : "bg-blue-500/10 text-blue-300 border-blue-500/30 hover:bg-blue-500/20"
                )}
                title="Click to view cache telemetry details & force refresh"
              >
                <span
                  className={cn(
                    "w-2 h-2 rounded-full",
                    cacheStatus?.is_warming
                      ? "bg-amber-400 animate-ping"
                      : cacheStatus?.source === "bigquery"
                      ? "bg-emerald-400"
                      : "bg-blue-400"
                  )}
                />
                <span className="font-semibold">
                  {cacheStatus?.is_warming
                    ? "Syncing BigQuery..."
                    : cacheStatus?.source === "bigquery"
                    ? `BigQuery Live (${cacheStatus.total_pools_cached.toLocaleString()} pools)`
                    : `Synthetic Mock (${cacheStatus?.total_pools_cached?.toLocaleString() || 6240} pools)`}
                </span>
              </button>

              {/* Cache Details Dropdown Popover */}
              {showCacheDetails && (
                <div
                  className="absolute right-0 mt-2 w-72 rounded-xl bg-slate-900 border border-slate-800 shadow-2xl p-4 z-50 text-xs font-mono"
                  onMouseLeave={() => setShowCacheDetails(false)}
                >
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                    <div className="flex items-center gap-1.5">
                      <Database className="w-3.5 h-3.5 text-cyan-400" />
                      <span className="text-slate-400 font-bold uppercase tracking-wider text-[10px]">
                        Cache Provenance
                      </span>
                    </div>
                    <span
                      className={cn(
                        "px-1.5 py-0.5 rounded text-[10px] font-bold uppercase",
                        cacheStatus?.source === "bigquery"
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                          : "bg-blue-500/20 text-blue-300 border border-blue-500/40"
                      )}
                    >
                      {cacheStatus?.source || "unknown"}
                    </span>
                  </div>

                  <div className="space-y-2 py-3 text-slate-300">
                    <div className="flex justify-between">
                      <span className="text-slate-400">Cached Pools:</span>
                      <span className="font-bold text-white">
                        {cacheStatus?.total_pools_cached.toLocaleString() ?? "N/A"}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Price Intervals:</span>
                      <span className="text-white">
                        {cacheStatus?.total_price_intervals.toLocaleString() ?? "N/A"}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Preemption Points:</span>
                      <span className="text-white">
                        {cacheStatus?.total_preemption_points.toLocaleString() ?? "N/A"}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Last Synced:</span>
                      <span className="text-slate-300">
                        {cacheStatus?.last_synced_at
                          ? new Date(cacheStatus.last_synced_at).toLocaleTimeString()
                          : "Boot Time"}
                      </span>
                    </div>
                  </div>

                  <button
                    onClick={() => {
                      setShowCacheDetails(false);
                      handleForceRefresh();
                    }}
                    disabled={isForceRefreshing}
                    className="w-full mt-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-300 border border-cyan-500/40 transition-colors cursor-pointer"
                  >
                    <RefreshCw className={cn("w-3 h-3", isForceRefreshing && "animate-spin")} />
                    <span>Force Refresh from BigQuery</span>
                  </button>
                </div>
              )}
            </div>

            <button
              onClick={loadAllData}
              disabled={isRefreshing || isForceRefreshing}
              className="p-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white transition-colors border border-slate-800 cursor-pointer"
              title="Refresh Telemetry Data"
            >
              <RefreshCw
                className={cn(
                  "w-4 h-4 text-slate-400",
                  (isRefreshing || isForceRefreshing) && "animate-spin text-cyan-400"
                )}
              />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {loading ? (
          <div className="py-24 text-center">
            <RefreshCw className="w-8 h-8 mx-auto text-cyan-400 animate-spin mb-3" />
            <p className="font-mono text-sm text-slate-400">
              Connecting to GCP Capacity History Engine...
            </p>
          </div>
        ) : (
          <>
            {activeTab === "situation-room" && (
              <SituationRoom
                anomalies={anomalies}
                totalPoolsCount={pools.length}
                watchlist={watchlist}
                onRefreshData={loadAllData}
                onRemoveWatchlistTarget={handleRemoveWatchlistTarget}
                onInspect={(a) =>
                  setInspectTarget({
                    region: a.region,
                    zone: a.zone,
                    machineType: a.machine_type,
                  })
                }
                onViewPivots={(a) =>
                  handleOpenPivots(a.region, a.zone, a.machine_type)
                }
              />
            )}

            {activeTab === "explorer" && (
              <PoolExplorer
                pools={pools}
                onSelectPool={(p) =>
                  setInspectTarget({
                    region: p.region,
                    zone: p.zone,
                    machineType: p.machine_type,
                  })
                }
                onViewPivots={(p) =>
                  handleOpenPivots(p.region, p.zone, p.machine_type)
                }
                onToggleWatchlist={handleToggleWatchlist}
              />
            )}

            {activeTab === "watchlist" && (
              <WatchlistManager
                watchlist={watchlist}
                onRefresh={loadAllData}
                onRemoveTarget={handleRemoveWatchlistTarget}
              />
            )}
          </>
        )}
      </main>

      {/* Modals */}
      {inspectTarget && (
        <InspectorModal
          isOpen={true}
          onClose={() => setInspectTarget(null)}
          region={inspectTarget.region}
          zone={inspectTarget.zone}
          machineType={inspectTarget.machineType}
          onOpenPivots={(r, z, m) => handleOpenPivots(r, z, m)}
        />
      )}

      {pivotTarget && (
        <PivotModal
          isOpen={true}
          onClose={() => setPivotTarget(null)}
          poolKey={pivotTarget.poolKey}
          pivots={pivotTarget.pivots}
        />
      )}

      {/* Footer */}
      <footer className="border-t border-slate-900 py-4 px-6 text-center text-xs font-mono text-slate-500 flex flex-col sm:flex-row items-center justify-between max-w-7xl mx-auto w-full">
        <div>
          MindTheSpot Engine &bull; Refreshed at {lastRefreshed || "Just now"}
        </div>
        <div className="flex items-center gap-4 mt-2 sm:mt-0">
          <a
            href="/api/docs"
            target="_blank"
            rel="noreferrer"
            className="hover:text-slate-300 flex items-center gap-1"
          >
            REST API Docs <ExternalLink className="w-3 h-3" />
          </a>
          <span>GCP Spot Preemption & Price Surveillance</span>
        </div>
      </footer>
    </div>
  );
};
