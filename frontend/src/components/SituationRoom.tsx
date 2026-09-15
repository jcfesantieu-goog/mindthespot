import React, { useState } from "react";
import {
  AlertTriangle,
  TrendingUp,
  Activity,
  Layers,
  Star,
  DollarSign,
  Filter,
} from "lucide-react";
import { AnomalyItem, Severity } from "../types";
import { AnomalyCard } from "./AnomalyCard";
import { cn } from "../lib/utils";

interface SituationRoomProps {
  anomalies: AnomalyItem[];
  totalPoolsCount: number;
  onInspect: (anomaly: AnomalyItem) => void;
  onViewPivots: (anomaly: AnomalyItem) => void;
}

export const SituationRoom: React.FC<SituationRoomProps> = ({
  anomalies,
  totalPoolsCount,
  onInspect,
  onViewPivots,
}) => {
  const [severityFilter, setSeverityFilter] = useState<Severity | "ALL">("ALL");
  const [regionFilter, setRegionFilter] = useState<string>("ALL");
  const [watchlistOnly, setWatchlistOnly] = useState<boolean>(false);

  const criticalCount = anomalies.filter((a) => a.severity === "CRITICAL").length;
  const elevatedCount = anomalies.filter((a) => a.severity === "ELEVATED").length;
  const priceHikeCount = anomalies.filter((a) => a.price_hike_detected).length;

  const regions = [
    "ALL",
    ...Array.from(new Set(anomalies.map((a) => a.region))),
  ];

  const filtered = anomalies.filter((a) => {
    if (watchlistOnly && !a.is_watchlist) return false;
    if (severityFilter !== "ALL" && a.severity !== severityFilter) return false;
    if (regionFilter !== "ALL" && a.region !== regionFilter) return false;
    return true;
  });

  return (
    <div className="space-y-6">
      {/* KPI Tiles Banner */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Monitored Pools */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 font-mono mb-1">Monitored Pools</div>
            <div className="text-2xl font-bold font-mono text-slate-100">{totalPoolsCount}</div>
            <div className="text-[11px] text-slate-500 font-mono mt-0.5">11 Tier-1 Families &bull; 43 Regions</div>
          </div>
          <div className="p-3 rounded-xl bg-slate-800 text-slate-300">
            <Layers className="w-5 h-5" />
          </div>
        </div>

        {/* Critical Regime Shifts */}
        <div className="bg-slate-900 border border-red-500/30 rounded-xl p-4 flex items-center justify-between">
          <div>
            <div className="text-xs text-red-400 font-mono mb-1">Critical Shifts</div>
            <div className="text-2xl font-bold font-mono text-red-400">{criticalCount}</div>
            <div className="text-[11px] text-red-300/60 font-mono mt-0.5">Z ≥ 2.5&sigma; or Rate &gt; 50%</div>
          </div>
          <div className="p-3 rounded-xl bg-red-500/20 text-red-400">
            <AlertTriangle className="w-5 h-5" />
          </div>
        </div>

        {/* Elevated Risk */}
        <div className="bg-slate-900 border border-amber-500/30 rounded-xl p-4 flex items-center justify-between">
          <div>
            <div className="text-xs text-amber-400 font-mono mb-1">Elevated Risk</div>
            <div className="text-2xl font-bold font-mono text-amber-400">{elevatedCount}</div>
            <div className="text-[11px] text-amber-300/60 font-mono mt-0.5">Z ≥ 1.8&sigma; or &Delta; &ge; 15%</div>
          </div>
          <div className="p-3 rounded-xl bg-amber-500/20 text-amber-400">
            <TrendingUp className="w-5 h-5" />
          </div>
        </div>

        {/* Spot Price Hikes */}
        <div className="bg-slate-900 border border-emerald-500/30 rounded-xl p-4 flex items-center justify-between">
          <div>
            <div className="text-xs text-emerald-400 font-mono mb-1">Spot Price Hikes</div>
            <div className="text-2xl font-bold font-mono text-emerald-400">{priceHikeCount}</div>
            <div className="text-[11px] text-emerald-300/60 font-mono mt-0.5">&ge; +10% Step Changes</div>
          </div>
          <div className="p-3 rounded-xl bg-emerald-500/20 text-emerald-400">
            <DollarSign className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-slate-400 font-mono flex items-center gap-1.5 mr-2">
            <Filter className="w-3.5 h-3.5" /> Filter Shifts:
          </span>

          {/* Severity Buttons */}
          <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs font-mono">
            {(["ALL", "CRITICAL", "ELEVATED"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSeverityFilter(s)}
                className={cn(
                  "px-3 py-1 rounded-md transition-all font-semibold",
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

          {/* Region Dropdown */}
          <select
            value={regionFilter}
            onChange={(e) => setRegionFilter(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500"
          >
            {regions.map((r) => (
              <option key={r} value={r}>
                {r === "ALL" ? "All Regions" : r}
              </option>
            ))}
          </select>
        </div>

        {/* Watchlist Toggle */}
        <button
          onClick={() => setWatchlistOnly(!watchlistOnly)}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium font-mono transition-colors border",
            watchlistOnly
              ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
              : "bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-200"
          )}
        >
          <Star className={cn("w-3.5 h-3.5", watchlistOnly && "fill-amber-400")} />
          <span>Watchlist Only</span>
        </button>
      </div>

      {/* Anomalies Cards Grid */}
      {filtered.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center text-slate-400">
          <Activity className="w-10 h-10 mx-auto text-emerald-400 mb-3" />
          <h3 className="text-base font-bold text-slate-200 font-mono">All Monitored Pools Stable</h3>
          <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto">
            No statistical regime shifts or critical preemption anomalies exceed the alerting threshold
            for the selected filters.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((anomaly) => (
            <AnomalyCard
              key={anomaly.pool_key}
              anomaly={anomaly}
              onInspect={onInspect}
              onViewPivots={onViewPivots}
            />
          ))}
        </div>
      )}
    </div>
  );
};
