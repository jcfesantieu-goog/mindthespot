import React, { useState, useEffect, useRef } from "react";
import {
  AlertTriangle,
  TrendingUp,
  Activity,
  Layers,
  Star,
  DollarSign,
  Filter,
  Info,
  ChevronDown,
  ChevronUp,
  ArrowUpRight,
  ArrowDownRight,
  Plus,
  Settings2,
} from "lucide-react";
import { AnomalyItem, Severity, WatchlistEntry, PoolHistory } from "../types";
import { fetchPoolHistory } from "../lib/api";
import { AnomalyCard } from "./AnomalyCard";
import { WatchlistModal } from "./WatchlistModal";
import { cn } from "../lib/utils";

interface SituationRoomProps {
  anomalies: AnomalyItem[];
  totalPoolsCount: number;
  watchlist?: WatchlistEntry[];
  onInspect: (anomaly: AnomalyItem) => void;
  onViewPivots: (anomaly: AnomalyItem) => void;
  onRefreshData?: () => void;
  onRemoveWatchlistTarget?: (entry: WatchlistEntry) => void;
}

export const SituationRoom: React.FC<SituationRoomProps> = ({
  anomalies,
  totalPoolsCount,
  watchlist = [],
  onInspect,
  onViewPivots,
  onRefreshData,
  onRemoveWatchlistTarget,
}) => {
  const [severityFilter, setSeverityFilter] = useState<Severity | "ALL">("ALL");
  const [priceFilter, setPriceFilter] = useState<"ALL" | "HIKE" | "DROP">("ALL");
  const [regionFilter, setRegionFilter] = useState<string>("ALL");
  const [selectedWatchlist, setSelectedWatchlist] = useState<string>("ALL");
  const [watchlistMenuOpen, setWatchlistMenuOpen] = useState<boolean>(false);
  const [watchlistModalOpen, setWatchlistModalOpen] = useState<boolean>(false);
  const [watchlistModalAddMode, setWatchlistModalAddMode] = useState<boolean>(false);
  const [showMethodology, setShowMethodology] = useState<boolean>(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Inline inspection state (identical to Fallback Pivot Recommendations and Pool Explorer)
  const [expandedAnomalyKey, setExpandedAnomalyKey] = useState<string | null>(null);
  const [historyCache, setHistoryCache] = useState<Record<string, PoolHistory>>({});
  const [loadingAnomalyKey, setLoadingAnomalyKey] = useState<string | null>(null);
  const [errorMap, setErrorMap] = useState<Record<string, string>>({});

  const handleToggleInspect = async (anomaly: AnomalyItem) => {
    if (expandedAnomalyKey === anomaly.pool_key) {
      setExpandedAnomalyKey(null);
      return;
    }

    setExpandedAnomalyKey(anomaly.pool_key);

    if (!historyCache[anomaly.pool_key] && loadingAnomalyKey !== anomaly.pool_key) {
      setLoadingAnomalyKey(anomaly.pool_key);
      try {
        const data = await fetchPoolHistory(anomaly.region, anomaly.zone, anomaly.machine_type);
        setHistoryCache((prev) => ({ ...prev, [anomaly.pool_key]: data }));
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "Failed to load telemetry";
        setErrorMap((prev) => ({
          ...prev,
          [anomaly.pool_key]: message,
        }));
      } finally {
        setLoadingAnomalyKey(null);
      }
    }
  };

  const criticalCount = anomalies.filter((a) => a.severity === "CRITICAL").length;
  const elevatedCount = anomalies.filter((a) => a.severity === "ELEVATED").length;
  const priceHikeCount = anomalies.filter((a) => a.price_hike_detected).length;
  const priceDropCount = anomalies.filter((a) => a.price_drop_detected).length;

  const regions = [
    "ALL",
    ...Array.from(new Set(anomalies.map((a) => a.region))).sort(),
  ];

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setWatchlistMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const anomalyMatchesWatchlist = (a: AnomalyItem, entry: WatchlistEntry) => {
    if (a.custom_label && entry.name && a.custom_label === entry.name) {
      return true;
    }
    if (a.region !== entry.region) return false;
    const zoneMatch = entry.zones.length === 0 || entry.zones.includes(a.zone);
    const mtMatch = entry.machine_types.length === 0 || entry.machine_types.includes(a.machine_type);
    return zoneMatch && mtMatch;
  };

  const filtered = anomalies.filter((a) => {
    if (selectedWatchlist === "WATCHLIST_ANY") {
      if (!a.is_watchlist) return false;
    } else if (selectedWatchlist !== "ALL") {
      const entry = watchlist.find(
        (w) => (w.name || `${w.region} Workload`) === selectedWatchlist
      );
      if (entry) {
        if (!anomalyMatchesWatchlist(a, entry)) return false;
      } else if (a.custom_label !== selectedWatchlist) {
        return false;
      }
    }
    if (severityFilter !== "ALL" && a.severity !== severityFilter) return false;
    if (regionFilter !== "ALL" && a.region !== regionFilter) return false;
    if (priceFilter === "HIKE" && !a.price_hike_detected) return false;
    if (priceFilter === "DROP" && !a.price_drop_detected) return false;
    return true;
  });

  return (
    <div className="space-y-6">
      {/* KPI Tiles Banner (5 Tiles) */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {/* Monitored Pools */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5 flex items-center justify-between">
          <div>
            <div className="text-[11px] text-slate-400 font-mono mb-0.5">Monitored Pools</div>
            <div className="text-2xl font-bold font-mono text-slate-100">{totalPoolsCount}</div>
            <div className="text-[10px] text-slate-500 font-mono mt-0.5">11 Families &bull; 43 Regions</div>
          </div>
          <div className="p-2.5 rounded-xl bg-slate-800 text-slate-300">
            <Layers className="w-4 h-4" />
          </div>
        </div>

        {/* Critical Regime Shifts */}
        <button
          onClick={() => {
            setSeverityFilter(severityFilter === "CRITICAL" ? "ALL" : "CRITICAL");
            setPriceFilter("ALL");
          }}
          className={cn(
            "text-left bg-slate-900 border rounded-xl p-3.5 flex items-center justify-between transition-all cursor-pointer hover:border-red-500/60",
            severityFilter === "CRITICAL" ? "border-red-500 bg-red-950/20 ring-1 ring-red-500/50" : "border-red-500/30"
          )}
        >
          <div>
            <div className="text-[11px] text-red-400 font-mono mb-0.5">Critical Shifts</div>
            <div className="text-2xl font-bold font-mono text-red-400">{criticalCount}</div>
            <div className="text-[10px] text-red-300/70 font-mono mt-0.5">Z ≥ 2.5&sigma; &bull; p &lt; 0.6%</div>
          </div>
          <div className="p-2.5 rounded-xl bg-red-500/20 text-red-400">
            <AlertTriangle className="w-4 h-4" />
          </div>
        </button>

        {/* Elevated Risk */}
        <button
          onClick={() => {
            setSeverityFilter(severityFilter === "ELEVATED" ? "ALL" : "ELEVATED");
            setPriceFilter("ALL");
          }}
          className={cn(
            "text-left bg-slate-900 border rounded-xl p-3.5 flex items-center justify-between transition-all cursor-pointer hover:border-amber-500/60",
            severityFilter === "ELEVATED" ? "border-amber-500 bg-amber-950/20 ring-1 ring-amber-500/50" : "border-amber-500/30"
          )}
        >
          <div>
            <div className="text-[11px] text-amber-400 font-mono mb-0.5">Elevated Risk</div>
            <div className="text-2xl font-bold font-mono text-amber-400">{elevatedCount}</div>
            <div className="text-[10px] text-amber-300/70 font-mono mt-0.5">Z ≥ 1.8&sigma; &bull; &Delta; &ge; 15%</div>
          </div>
          <div className="p-2.5 rounded-xl bg-amber-500/20 text-amber-400">
            <TrendingUp className="w-4 h-4" />
          </div>
        </button>

        {/* Spot Price Hikes */}
        <button
          onClick={() => {
            setPriceFilter(priceFilter === "HIKE" ? "ALL" : "HIKE");
            setSeverityFilter("ALL");
          }}
          className={cn(
            "text-left bg-slate-900 border rounded-xl p-3.5 flex items-center justify-between transition-all cursor-pointer hover:border-rose-500/60",
            priceFilter === "HIKE" ? "border-rose-500 bg-rose-950/20 ring-1 ring-rose-500/50" : "border-rose-500/30"
          )}
        >
          <div>
            <div className="text-[11px] text-rose-400 font-mono mb-0.5">Spot Price Hikes</div>
            <div className="text-2xl font-bold font-mono text-rose-400">{priceHikeCount}</div>
            <div className="text-[10px] text-rose-300/70 font-mono mt-0.5">&ge; +5% Step Hikes</div>
          </div>
          <div className="p-2.5 rounded-xl bg-rose-500/20 text-rose-400">
            <ArrowUpRight className="w-4 h-4" />
          </div>
        </button>

        {/* Spot Price Drops */}
        <button
          onClick={() => {
            setPriceFilter(priceFilter === "DROP" ? "ALL" : "DROP");
            setSeverityFilter("ALL");
          }}
          className={cn(
            "text-left bg-slate-900 border rounded-xl p-3.5 flex items-center justify-between transition-all cursor-pointer hover:border-emerald-500/60",
            priceFilter === "DROP" ? "border-emerald-500 bg-emerald-950/20 ring-1 ring-emerald-500/50" : "border-emerald-500/30"
          )}
        >
          <div>
            <div className="text-[11px] text-emerald-400 font-mono mb-0.5">Spot Price Drops</div>
            <div className="text-2xl font-bold font-mono text-emerald-400">{priceDropCount}</div>
            <div className="text-[10px] text-emerald-300/70 font-mono mt-0.5">&le; -5% Cost Savings</div>
          </div>
          <div className="p-2.5 rounded-xl bg-emerald-500/20 text-emerald-400">
            <ArrowDownRight className="w-4 h-4" />
          </div>
        </button>
      </div>

      {/* Methodology Explainer Banner */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden transition-all">
        <button
          onClick={() => setShowMethodology(!showMethodology)}
          className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-slate-850/60 transition-colors"
        >
          <div className="flex items-center gap-2.5">
            <div className="p-1 rounded bg-cyan-500/20 text-cyan-400">
              <Info className="w-4 h-4" />
            </div>
            <div>
              <span className="text-xs font-bold font-mono text-slate-200">
                Understanding Regime Shifts: Critical (Z ≥ 2.5σ) vs Elevated Risk (Z ≥ 1.8σ)
              </span>
              <span className="hidden sm:inline text-xs text-slate-400 font-mono ml-2">
                &bull; Two-window rolling statistics &amp; variance flooring
              </span>
            </div>
          </div>
          <div className="text-slate-400">
            {showMethodology ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </div>
        </button>

        {showMethodology && (
          <div className="px-5 pb-5 pt-2 border-t border-slate-800/80 text-xs font-mono space-y-3 bg-slate-950/40">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-3.5 rounded-lg bg-red-950/20 border border-red-500/30">
                <div className="flex items-center gap-2 text-red-400 font-bold mb-1.5">
                  <AlertTriangle className="w-4 h-4" />
                  <span>Critical Shift (Z ≥ 2.5σ or Rate &gt; 50%)</span>
                </div>
                <p className="text-slate-300 text-[11px] leading-relaxed">
                  Represents an extreme surge in Spot preemptions exceeding 2.5 standard deviations above the 23-day historical baseline. In statistical distribution terms, this represents a tail event with probability <strong>p &lt; 0.6%</strong>. High probability of immediate VM eviction. Active workloads should execute fallback pivots immediately.
                </p>
              </div>

              <div className="p-3.5 rounded-lg bg-amber-950/20 border border-amber-500/30">
                <div className="flex items-center gap-2 text-amber-400 font-bold mb-1.5">
                  <TrendingUp className="w-4 h-4" />
                  <span>Elevated Risk (Z ≥ 1.8σ or Δ ≥ +15%)</span>
                </div>
                <p className="text-slate-300 text-[11px] leading-relaxed">
                  Indicates meaningful upward preemption drift above 1.8 standard deviations (<strong>p &lt; 3.6%</strong>) or an absolute rate jump of &ge;15%. Serves as an early warning system allowing operations teams to diversify instances to sibling zones before critical contention is reached.
                </p>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-[11px] text-slate-400 flex flex-col md:flex-row items-start md:items-center justify-between gap-2">
              <div>
                <strong className="text-slate-200">Mathematical Formula:</strong>{" "}
                <span className="text-cyan-300">Z = (μ_recent_7d - μ_baseline_23d) / max(σ_baseline, 0.02)</span>
              </div>
              <div className="text-slate-400">
                <strong className="text-slate-300">Variance Floor (0.02):</strong> Eliminates false positives when historical evictions were zero or perfectly flat.
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Filter Toolbar */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-slate-400 font-mono flex items-center gap-1 mr-1">
            <Filter className="w-3.5 h-3.5" /> Severity:
          </span>

          {/* Severity Buttons */}
          <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs font-mono">
            {(["ALL", "CRITICAL", "ELEVATED"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSeverityFilter(s)}
                className={cn(
                  "px-2.5 py-1 rounded-md transition-all font-semibold",
                  severityFilter === s
                    ? s === "CRITICAL"
                      ? "bg-red-500/20 text-red-400 border border-red-500/40"
                      : s === "ELEVATED"
                      ? "bg-amber-500/20 text-amber-400 border border-amber-500/40"
                      : "bg-slate-800 text-slate-100"
                    : "text-slate-400 hover:text-slate-200"
                )}
              >
                {s}
              </button>
            ))}
          </div>

          {/* Price Shifts Filter Chips */}
          <span className="text-xs text-slate-400 font-mono flex items-center gap-1 ml-2 mr-1">
            <DollarSign className="w-3.5 h-3.5 text-slate-400" /> Price Shifts:
          </span>
          <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs font-mono">
            <button
              onClick={() => setPriceFilter("ALL")}
              className={cn(
                "px-2.5 py-1 rounded-md transition-all font-semibold",
                priceFilter === "ALL" ? "bg-slate-800 text-slate-100" : "text-slate-400 hover:text-slate-200"
              )}
            >
              All
            </button>
            <button
              onClick={() => setPriceFilter("HIKE")}
              className={cn(
                "flex items-center gap-1 px-2.5 py-1 rounded-md transition-all font-semibold",
                priceFilter === "HIKE"
                  ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                  : "text-slate-400 hover:text-rose-300"
              )}
            >
              <ArrowUpRight className="w-3 h-3 text-rose-400" />
              <span>Hikes ({priceHikeCount})</span>
            </button>
            <button
              onClick={() => setPriceFilter("DROP")}
              className={cn(
                "flex items-center gap-1 px-2.5 py-1 rounded-md transition-all font-semibold",
                priceFilter === "DROP"
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                  : "text-slate-400 hover:text-emerald-300"
              )}
            >
              <ArrowDownRight className="w-3 h-3 text-emerald-400" />
              <span>Drops ({priceDropCount})</span>
            </button>
          </div>

          {/* Region Dropdown */}
          <select
            value={regionFilter}
            onChange={(e) => setRegionFilter(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500 ml-1"
          >
            {regions.map((r) => (
              <option key={r} value={r}>
                {r === "ALL" ? "All Regions" : r}
              </option>
            ))}
          </select>
        </div>

        {/* Multi-Watchlist Dropdown */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setWatchlistMenuOpen(!watchlistMenuOpen)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium font-mono transition-colors border",
              selectedWatchlist !== "ALL"
                ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                : "bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-200"
            )}
            title="Filter by Watchlists or Manage Workloads"
          >
            <Star className={cn("w-3.5 h-3.5", selectedWatchlist !== "ALL" && "fill-amber-400 text-amber-400")} />
            <span>
              {selectedWatchlist === "ALL"
                ? `Watchlists (${watchlist.length})`
                : selectedWatchlist === "WATCHLIST_ANY"
                ? `All Watchlists (${anomalies.filter((a) => a.is_watchlist).length})`
                : `${selectedWatchlist}`}
            </span>
            <ChevronDown className={cn("w-3 h-3 transition-transform", watchlistMenuOpen && "rotate-180")} />
          </button>

          {/* Watchlists Popover Menu */}
          {watchlistMenuOpen && (
            <div className="absolute right-0 mt-2 w-72 bg-slate-900 border border-slate-800 rounded-xl shadow-2xl z-50 p-2 font-mono text-xs animate-in fade-in zoom-in-95 duration-100">
              <div className="px-2 py-1.5 flex items-center justify-between border-b border-slate-800 text-slate-400">
                <span className="font-bold text-[11px] uppercase tracking-wider">Workload Watchlists</span>
                <button
                  onClick={() => {
                    setWatchlistMenuOpen(false);
                    setWatchlistModalAddMode(false);
                    setWatchlistModalOpen(true);
                  }}
                  className="text-cyan-400 hover:text-cyan-300 text-[10px] flex items-center gap-1"
                >
                  <Settings2 className="w-3 h-3" />
                  <span>Manage</span>
                </button>
              </div>

              <div className="py-1 space-y-0.5 max-h-60 overflow-y-auto">
                <button
                  onClick={() => {
                    setSelectedWatchlist("ALL");
                    setWatchlistMenuOpen(false);
                  }}
                  className={cn(
                    "w-full text-left px-2.5 py-1.5 rounded-lg flex items-center justify-between transition-colors",
                    selectedWatchlist === "ALL"
                      ? "bg-slate-800 text-cyan-300 font-semibold"
                      : "text-slate-300 hover:bg-slate-800/60"
                  )}
                >
                  <span>All Monitored Pools</span>
                  <span className="text-[10px] text-slate-500">{totalPoolsCount}</span>
                </button>

                <button
                  onClick={() => {
                    setSelectedWatchlist("WATCHLIST_ANY");
                    setWatchlistMenuOpen(false);
                  }}
                  className={cn(
                    "w-full text-left px-2.5 py-1.5 rounded-lg flex items-center justify-between transition-colors",
                    selectedWatchlist === "WATCHLIST_ANY"
                      ? "bg-amber-500/20 text-amber-300 font-semibold"
                      : "text-slate-300 hover:bg-slate-800/60"
                  )}
                >
                  <div className="flex items-center gap-1.5">
                    <Star className="w-3 h-3 text-amber-400 fill-amber-400" />
                    <span>All Watchlists</span>
                  </div>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 font-bold">
                    {anomalies.filter((a) => a.is_watchlist).length}
                  </span>
                </button>

                {watchlist.length > 0 && (
                  <div className="pt-1.5 border-t border-slate-800/80 my-1">
                    <div className="px-2 pb-1 text-[10px] text-slate-500 uppercase tracking-wider font-semibold">
                      Named Watchlists
                    </div>
                    {watchlist.map((entry, idx) => {
                      const entryLabel = entry.name || `${entry.region} Workload`;
                      const count = anomalies.filter((a) => anomalyMatchesWatchlist(a, entry)).length;
                      const hasCritical = anomalies.some(
                        (a) => anomalyMatchesWatchlist(a, entry) && a.severity === "CRITICAL"
                      );
                      const isSelected = selectedWatchlist === entryLabel;

                      return (
                        <button
                          key={`${entry.region}-${entry.name || idx}`}
                          onClick={() => {
                            setSelectedWatchlist(entryLabel);
                            setWatchlistMenuOpen(false);
                          }}
                          className={cn(
                            "w-full text-left px-2.5 py-1.5 rounded-lg flex items-center justify-between transition-colors",
                            isSelected
                              ? "bg-amber-500/20 text-amber-300 font-semibold"
                              : "text-slate-300 hover:bg-slate-800/60"
                          )}
                        >
                          <div className="flex items-center gap-1.5 truncate pr-2">
                            <span className="truncate">{entryLabel}</span>
                            <span className="text-[9px] px-1 rounded bg-slate-800 text-slate-400 shrink-0">
                              {entry.region}
                            </span>
                          </div>
                          <span
                            className={cn(
                              "text-[10px] px-1.5 py-0.5 rounded font-bold shrink-0",
                              hasCritical
                                ? "bg-rose-500/20 text-rose-400"
                                : count > 0
                                ? "bg-amber-500/20 text-amber-400"
                                : "bg-slate-800 text-slate-500"
                            )}
                          >
                            {count}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="pt-1.5 border-t border-slate-800 flex flex-col gap-1">
                <button
                  onClick={() => {
                    setWatchlistMenuOpen(false);
                    setWatchlistModalAddMode(true);
                    setWatchlistModalOpen(true);
                  }}
                  className="w-full text-left px-2 py-1.5 rounded-lg text-amber-400 hover:bg-amber-500/10 transition-colors flex items-center gap-1.5 text-xs font-semibold"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add New Watchlist...</span>
                </button>
                <button
                  onClick={() => {
                    setWatchlistMenuOpen(false);
                    setWatchlistModalAddMode(false);
                    setWatchlistModalOpen(true);
                  }}
                  className="w-full text-left px-2 py-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors flex items-center gap-1.5 text-xs"
                >
                  <Settings2 className="w-3.5 h-3.5" />
                  <span>Manage All Watchlists...</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Anomalies Cards Grid */}
      {filtered.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center text-slate-400">
          <Activity className="w-10 h-10 mx-auto text-emerald-400 mb-3" />
          <h3 className="text-base font-bold text-slate-200 font-mono">No Matching Regime Shifts</h3>
          <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto">
            No statistical regime shifts or pricing anomalies exceed the alerting threshold
            for the selected filters.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((anomaly) => (
            <AnomalyCard
              key={anomaly.pool_key}
              anomaly={anomaly}
              isExpanded={expandedAnomalyKey === anomaly.pool_key}
              isLoading={loadingAnomalyKey === anomaly.pool_key}
              history={historyCache[anomaly.pool_key]}
              error={errorMap[anomaly.pool_key]}
              onToggleInspect={handleToggleInspect}
              onInspect={onInspect}
              onViewPivots={onViewPivots}
            />
          ))}
        </div>
      )}

      {/* Watchlist Management Modal */}
      <WatchlistModal
        isOpen={watchlistModalOpen}
        onClose={() => setWatchlistModalOpen(false)}
        watchlist={watchlist}
        onRefreshData={onRefreshData}
        onRemoveTarget={onRemoveWatchlistTarget}
        initialAddMode={watchlistModalAddMode}
      />
    </div>
  );
};
