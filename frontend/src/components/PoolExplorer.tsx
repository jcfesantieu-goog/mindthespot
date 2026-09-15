import React, { useState } from "react";
import { Search, Star, Shuffle, Eye } from "lucide-react";
import { PoolSummary } from "../types";
import { cn, formatPercent, formatPrice } from "../lib/utils";

interface PoolExplorerProps {
  pools: PoolSummary[];
  onSelectPool: (pool: PoolSummary) => void;
  onViewPivots: (pool: PoolSummary) => void;
}

export const PoolExplorer: React.FC<PoolExplorerProps> = ({
  pools,
  onSelectPool,
  onViewPivots,
}) => {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedRegion, setSelectedRegion] = useState<string>("ALL");
  const [selectedFamily, setSelectedFamily] = useState<string>("ALL");
  const [watchlistOnly, setWatchlistOnly] = useState<boolean>(false);

  const families = ["ALL", "c4d", "c3d", "c4a", "c3", "c2", "n2d", "n2", "e2"];
  const regions = [
    "ALL",
    "europe-west4",
    "europe-west1",
    "europe-west9",
    "us-central1",
    "us-east4",
    "us-west1",
  ];

  const filteredPools = pools.filter((p) => {
    if (watchlistOnly && !p.is_watchlist) return false;
    if (selectedRegion !== "ALL" && p.region !== selectedRegion) return false;
    if (selectedFamily !== "ALL" && p.family !== selectedFamily) return false;
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      return (
        p.pool_key.toLowerCase().includes(q) ||
        (p.custom_label || "").toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <div className="space-y-4">
      {/* Controls Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        {/* Search Input */}
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search by instance, zone, or custom workload label..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-xs font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
          />
        </div>

        {/* Region Dropdown */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-slate-400 font-mono">Region:</label>
          <select
            value={selectedRegion}
            onChange={(e) => setSelectedRegion(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500"
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
            "flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors border",
            watchlistOnly
              ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
              : "bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-200"
          )}
        >
          <Star className={cn("w-3.5 h-3.5", watchlistOnly && "fill-amber-400")} />
          <span>Watchlist Only</span>
        </button>
      </div>

      {/* Family Filters */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs font-mono">
        <span className="text-slate-400 mr-1 text-[11px] uppercase tracking-wider font-semibold">
          Family:
        </span>
        {families.map((fam) => (
          <button
            key={fam}
            onClick={() => setSelectedFamily(fam)}
            className={cn(
              "px-3 py-1 rounded-md transition-all font-semibold uppercase tracking-wider",
              selectedFamily === fam
                ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/50 shadow-sm shadow-cyan-900/30"
                : "bg-slate-900 text-slate-400 border border-slate-800 hover:text-slate-200 hover:bg-slate-850"
            )}
          >
            {fam}
          </button>
        ))}
      </div>

      {/* Results Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider border-b border-slate-800 text-[11px]">
              <tr>
                <th className="py-3 px-4">Pool / Machine Type</th>
                <th className="py-3 px-4">Region / Zone</th>
                <th className="py-3 px-4">Family</th>
                <th className="py-3 px-4">7d Recent Avg</th>
                <th className="py-3 px-4">30d Avg</th>
                <th className="py-3 px-4">Hourly Spot</th>
                <th className="py-3 px-4">Severity</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {filteredPools.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-500 font-sans">
                    No instance pools match the selected filters.
                  </td>
                </tr>
              ) : (
                filteredPools.map((pool) => {
                  const isCritical = pool.severity === "CRITICAL";
                  const isElevated = pool.severity === "ELEVATED";

                  return (
                    <tr
                      key={pool.pool_key}
                      className="hover:bg-slate-850/50 transition-colors group"
                    >
                      <td className="py-3 px-4 font-bold text-slate-200">
                        <div className="flex items-center gap-1.5">
                          {pool.is_watchlist && (
                            <Star className="w-3.5 h-3.5 text-amber-400 fill-amber-400 flex-shrink-0" />
                          )}
                          <span>{pool.machine_type}</span>
                          {pool.custom_label && (
                            <span className="text-[10px] text-amber-300 bg-amber-950/60 px-1.5 py-0.5 rounded border border-amber-800/40">
                              {pool.custom_label}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {pool.region} &bull; <span className="text-slate-400">{pool.zone}</span>
                      </td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 font-bold uppercase text-[10px]">
                          {pool.family}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={cn(
                            "font-bold",
                            isCritical
                              ? "text-red-400"
                              : isElevated
                              ? "text-amber-400"
                              : "text-slate-300"
                          )}
                        >
                          {formatPercent(pool.avg_7d_rate)}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-slate-400">{formatPercent(pool.avg_30d_rate)}</td>
                      <td className="py-3 px-4 text-emerald-400 font-semibold">
                        {formatPrice(pool.hourly_price)}
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={cn(
                            "px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border",
                            isCritical
                              ? "bg-red-500/20 text-red-400 border-red-500/40"
                              : isElevated
                              ? "bg-amber-500/20 text-amber-400 border-amber-500/40"
                              : "bg-emerald-500/20 text-emerald-400 border-emerald-500/40"
                          )}
                        >
                          {pool.severity}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => onSelectPool(pool)}
                            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
                            title="Inspect 30d Curve"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </button>
                          {(isCritical || isElevated) && (
                            <button
                              onClick={() => onViewPivots(pool)}
                              className="p-1.5 rounded-lg bg-cyan-600/30 hover:bg-cyan-600 text-cyan-300 hover:text-white transition-colors border border-cyan-500/40"
                              title="View Pivot Fallbacks"
                            >
                              <Shuffle className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        <div className="px-4 py-2.5 bg-slate-950/60 border-t border-slate-800 text-[11px] text-slate-400 flex items-center justify-between font-mono">
          <span>Showing {filteredPools.length} of {pools.length} active instance pools</span>
        </div>
      </div>
    </div>
  );
};
