import React, { useState } from "react";
import { Search, Star, Shuffle, Eye, ChevronLeft, ChevronRight } from "lucide-react";
import { PoolSummary } from "../types";
import { cn, formatPercent, formatPrice } from "../lib/utils";

interface PoolExplorerProps {
  pools: PoolSummary[];
  onSelectPool: (pool: PoolSummary) => void;
  onViewPivots: (pool: PoolSummary) => void;
  onToggleWatchlist?: (pool: PoolSummary) => void;
}

export const PoolExplorer: React.FC<PoolExplorerProps> = ({
  pools,
  onSelectPool,
  onViewPivots,
  onToggleWatchlist,
}) => {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedRegion, setSelectedRegion] = useState<string>("ALL");
  const [selectedFamily, setSelectedFamily] = useState<string>("ALL");
  const [watchlistOnly, setWatchlistOnly] = useState<boolean>(false);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(50);

  type SortField =
    | "machine_type"
    | "region"
    | "family"
    | "avg_7d_rate"
    | "avg_30d_rate"
    | "hourly_price"
    | "spot_discount_pct"
    | "severity";

  const [sortField, setSortField] = useState<SortField | null>(null);
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  // Dynamically extract unique regions and families from loaded pools
  const regions = [
    "ALL",
    ...Array.from(new Set(pools.map((p) => p.region))).sort(),
  ];

  const families = [
    "ALL",
    ...Array.from(new Set(pools.map((p) => p.family))).sort(),
  ];

  const handleSearchChange = (val: string) => {
    setSearchTerm(val);
    setCurrentPage(1);
  };

  const handleRegionChange = (reg: string) => {
    setSelectedRegion(reg);
    setCurrentPage(1);
  };

  const handleFamilyChange = (fam: string) => {
    setSelectedFamily(fam);
    setCurrentPage(1);
  };

  const handleWatchlistToggle = () => {
    setWatchlistOnly(!watchlistOnly);
    setCurrentPage(1);
  };

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      if (sortOrder === "desc") {
        setSortOrder("asc");
      } else {
        setSortField(null);
        setSortOrder("desc");
      }
    } else {
      setSortField(field);
      setSortOrder(
        field === "spot_discount_pct" || field === "avg_7d_rate" || field === "avg_30d_rate"
          ? "desc"
          : "asc"
      );
    }
    setCurrentPage(1);
  };

  const filteredPools = pools.filter((p) => {
    if (watchlistOnly && !p.is_watchlist) return false;
    if (selectedRegion !== "ALL" && p.region !== selectedRegion) return false;
    if (selectedFamily !== "ALL" && p.family !== selectedFamily) return false;
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      return (
        p.pool_key.toLowerCase().includes(q) ||
        (p.custom_label || "").toLowerCase().includes(q) ||
        p.region.toLowerCase().includes(q) ||
        p.zone.toLowerCase().includes(q) ||
        p.family.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const sortedPools = [...filteredPools].sort((a, b) => {
    if (!sortField) return 0;
    let comparison = 0;
    if (sortField === "machine_type") {
      comparison = a.machine_type.localeCompare(b.machine_type);
    } else if (sortField === "region") {
      comparison = a.region.localeCompare(b.region);
    } else if (sortField === "family") {
      comparison = a.family.localeCompare(b.family);
    } else if (sortField === "avg_7d_rate") {
      comparison = a.avg_7d_rate - b.avg_7d_rate;
    } else if (sortField === "avg_30d_rate") {
      comparison = a.avg_30d_rate - b.avg_30d_rate;
    } else if (sortField === "hourly_price") {
      comparison = a.hourly_price - b.hourly_price;
    } else if (sortField === "spot_discount_pct") {
      comparison = (a.spot_discount_pct ?? 0) - (b.spot_discount_pct ?? 0);
    } else if (sortField === "severity") {
      const order = { CRITICAL: 3, ELEVATED: 2, STABLE: 1 };
      comparison = (order[a.severity] || 0) - (order[b.severity] || 0);
    }
    return sortOrder === "asc" ? comparison : -comparison;
  });

  // Client-side pagination calculation to prevent DOM overload
  const totalItems = sortedPools.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const activePage = Math.min(currentPage, totalPages);
  const startIdx = totalItems === 0 ? 0 : (activePage - 1) * pageSize;
  const endIdx = Math.min(startIdx + pageSize, totalItems);
  const paginatedPools = sortedPools.slice(startIdx, endIdx);

  return (
    <div className="space-y-4">
      {/* Controls Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        {/* Search Input */}
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search by instance, zone, region, or custom workload label..."
            value={searchTerm}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-xs font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
          />
        </div>

        {/* Region Dropdown */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-slate-400 font-mono">Region:</label>
          <select
            value={selectedRegion}
            onChange={(e) => handleRegionChange(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500 max-w-[200px]"
          >
            {regions.map((r) => (
              <option key={r} value={r}>
                {r === "ALL" ? `All Regions (${regions.length - 1})` : r}
              </option>
            ))}
          </select>
        </div>

        {/* Watchlist Toggle */}
        <button
          onClick={handleWatchlistToggle}
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
            onClick={() => handleFamilyChange(fam)}
            className={cn(
              "px-3 py-1 rounded-md transition-all font-semibold uppercase tracking-wider whitespace-nowrap",
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
                <th
                  onClick={() => handleSort("machine_type")}
                  className="py-3 px-4 cursor-pointer hover:text-cyan-300 transition-colors select-none"
                >
                  <div className="flex items-center gap-1">
                    <span>Pool / Machine Type</span>
                    {sortField === "machine_type" && (sortOrder === "asc" ? "▲" : "▼")}
                  </div>
                </th>
                <th
                  onClick={() => handleSort("region")}
                  className="py-3 px-4 cursor-pointer hover:text-cyan-300 transition-colors select-none"
                >
                  <div className="flex items-center gap-1">
                    <span>Region / Zone</span>
                    {sortField === "region" && (sortOrder === "asc" ? "▲" : "▼")}
                  </div>
                </th>
                <th
                  onClick={() => handleSort("family")}
                  className="py-3 px-4 cursor-pointer hover:text-cyan-300 transition-colors select-none"
                >
                  <div className="flex items-center gap-1">
                    <span>Family</span>
                    {sortField === "family" && (sortOrder === "asc" ? "▲" : "▼")}
                  </div>
                </th>
                <th
                  onClick={() => handleSort("avg_7d_rate")}
                  className="py-3 px-4 cursor-pointer hover:text-cyan-300 transition-colors select-none"
                >
                  <div className="flex items-center gap-1">
                    <span>7d Recent Avg</span>
                    {sortField === "avg_7d_rate" && (sortOrder === "asc" ? "▲" : "▼")}
                  </div>
                </th>
                <th
                  onClick={() => handleSort("avg_30d_rate")}
                  className="py-3 px-4 cursor-pointer hover:text-cyan-300 transition-colors select-none"
                >
                  <div className="flex items-center gap-1">
                    <span>30d Avg</span>
                    {sortField === "avg_30d_rate" && (sortOrder === "asc" ? "▲" : "▼")}
                  </div>
                </th>
                <th
                  onClick={() => handleSort("hourly_price")}
                  className="py-3 px-4 cursor-pointer hover:text-cyan-300 transition-colors select-none"
                >
                  <div className="flex items-center gap-1">
                    <span>Hourly Spot</span>
                    {sortField === "hourly_price" && (sortOrder === "asc" ? "▲" : "▼")}
                  </div>
                </th>
                <th
                  onClick={() => handleSort("spot_discount_pct")}
                  className="py-3 px-4 cursor-pointer hover:text-cyan-300 transition-colors select-none"
                >
                  <div className="flex items-center gap-1">
                    <span>Spot Discount</span>
                    {sortField === "spot_discount_pct" && (sortOrder === "asc" ? "▲" : "▼")}
                  </div>
                </th>
                <th
                  onClick={() => handleSort("severity")}
                  className="py-3 px-4 cursor-pointer hover:text-cyan-300 transition-colors select-none"
                >
                  <div className="flex items-center gap-1">
                    <span>Severity</span>
                    {sortField === "severity" && (sortOrder === "asc" ? "▲" : "▼")}
                  </div>
                </th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {paginatedPools.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-slate-500 font-sans">
                    No instance pools match the selected filters.
                  </td>
                </tr>
              ) : (
                paginatedPools.map((pool) => {
                  const isCritical = pool.severity === "CRITICAL";
                  const isElevated = pool.severity === "ELEVATED";

                  return (
                    <tr
                      key={pool.pool_key}
                      className="hover:bg-slate-850/50 transition-colors group"
                    >
                      <td className="py-3 px-4 font-bold text-slate-200">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onToggleWatchlist?.(pool);
                            }}
                            className="p-1 rounded hover:bg-slate-800 transition-colors"
                            title={pool.is_watchlist ? "Remove from Watchlist" : "Add to Watchlist"}
                          >
                            <Star
                              className={cn(
                                "w-4 h-4 transition-colors",
                                pool.is_watchlist
                                  ? "text-amber-400 fill-amber-400"
                                  : "text-slate-600 hover:text-amber-400"
                              )}
                            />
                          </button>
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
                      <td className="py-3 px-4">
                        <div className="flex flex-col font-mono">
                          <div className="flex items-center gap-1.5">
                            <span className="text-emerald-400 font-semibold">
                              {formatPrice(pool.hourly_price)}
                            </span>
                            {pool.price_hike_detected && (
                              <span
                                className="text-[10px] text-rose-300 font-bold bg-rose-950/60 px-1 py-0.2 rounded border border-rose-800/40"
                                title="Recent Spot Price Hike"
                              >
                                ↗
                              </span>
                            )}
                            {pool.price_drop_detected && (
                              <span
                                className="text-[10px] text-emerald-300 font-bold bg-emerald-950/60 px-1 py-0.2 rounded border border-emerald-800/40"
                                title="Recent Spot Price Drop"
                              >
                                ↘
                              </span>
                            )}
                          </div>
                          {pool.ondemand_hourly_price && (
                            <span className="text-[10px] text-slate-500 line-through decoration-slate-600">
                              OD: {formatPrice(pool.ondemand_hourly_price)}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        {pool.spot_discount_pct !== undefined && pool.spot_discount_pct !== null ? (
                          <span
                            className="inline-flex items-center text-[11px] text-emerald-400 font-bold bg-emerald-950/70 px-2 py-0.5 rounded border border-emerald-800/40 font-mono"
                            title={
                              pool.ondemand_hourly_price
                                ? `${pool.spot_discount_pct.toFixed(1)}% savings vs on-demand list price (${formatPrice(pool.ondemand_hourly_price)})`
                                : `${pool.spot_discount_pct.toFixed(1)}% discount`
                            }
                          >
                            -{pool.spot_discount_pct.toFixed(1)}%
                          </span>
                        ) : (
                          <span className="text-slate-600 font-mono text-[11px]">--</span>
                        )}
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

        {/* Pagination & Summary Footer */}
        <div className="px-4 py-3 bg-slate-950/60 border-t border-slate-800 text-xs text-slate-400 flex flex-col sm:flex-row items-center justify-between gap-3 font-mono">
          <div className="flex items-center gap-2">
            <span>
              Showing {totalItems === 0 ? 0 : startIdx + 1}–{endIdx} of{" "}
              <strong className="text-slate-200">{totalItems}</strong> matching pools (from{" "}
              {pools.length} total across {regions.length - 1} regions)
            </span>
          </div>

          <div className="flex items-center gap-4">
            {/* Rows per page selector */}
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-slate-500">Rows:</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setCurrentPage(1);
                }}
                className="bg-slate-900 border border-slate-800 rounded px-2 py-1 text-xs text-slate-300 focus:outline-none focus:border-cyan-500"
              >
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={250}>250</option>
              </select>
            </div>

            {/* Page navigation controls */}
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={activePage <= 1}
                className="p-1 rounded bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                title="Previous Page"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-[11px] px-1 text-slate-300">
                Page {activePage} of {totalPages}
              </span>
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={activePage >= totalPages}
                className="p-1 rounded bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                title="Next Page"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
