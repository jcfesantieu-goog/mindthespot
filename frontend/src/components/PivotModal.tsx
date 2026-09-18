import React, { useState } from "react";
import {
  X,
  Shuffle,
  ArrowRight,
  Layers,
  MapPin,
  TrendingDown,
  TrendingUp,
  DollarSign,
  Eye,
  ShieldCheck,
  Activity,
  Loader2,
} from "lucide-react";
import { PivotCandidate, PoolHistory } from "../types";
import { fetchPoolHistory } from "../lib/api";
import { PreemptionChart } from "./PreemptionChart";
import { PriceTimeline } from "./PriceTimeline";
import {
  cn,
  formatPercent,
  formatPrice,
  formatSignedPercent,
  formatSignedZScore,
  getDiscountTier,
  getDiscountTierBadgeClass,
  getDiscountTierLabel,
} from "../lib/utils";

interface PivotModalProps {
  isOpen: boolean;
  onClose: () => void;
  poolKey: string;
  pivots: PivotCandidate[];
  onInspectPool?: (pool: { region: string; zone: string; machine_type: string }) => void;
}

export const PivotModal: React.FC<PivotModalProps> = ({
  isOpen,
  onClose,
  poolKey,
  pivots,
}) => {
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [historyCache, setHistoryCache] = useState<Record<string, PoolHistory>>({});
  const [loadingKey, setLoadingKey] = useState<string | null>(null);
  const [errorMap, setErrorMap] = useState<Record<string, string>>({});

  if (!isOpen) return null;

  const handleToggleInspect = async (
    candidateKey: string,
    region: string,
    zone: string,
    machineType: string
  ) => {
    if (expandedKey === candidateKey) {
      setExpandedKey(null);
      return;
    }

    setExpandedKey(candidateKey);

    if (!historyCache[candidateKey] && loadingKey !== candidateKey) {
      setLoadingKey(candidateKey);
      try {
        const data = await fetchPoolHistory(region, zone, machineType);
        setHistoryCache((prev) => ({ ...prev, [candidateKey]: data }));
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "Failed to load telemetry";
        setErrorMap((prev) => ({
          ...prev,
          [candidateKey]: message,
        }));
      } finally {
        setLoadingKey(null);
      }
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-5xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 text-slate-100">
        {/* Header */}
        <div className="flex items-start justify-between pb-4 border-b border-slate-800 mb-6">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
              <Shuffle className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold font-mono">
                Fallback Pivot Recommendations
              </h2>
              <p className="text-xs text-slate-400 font-mono mt-0.5">
                Target Congested Pool: <span className="text-red-400 font-semibold">{poolKey}</span>
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Pivot List */}
        {pivots.length === 0 ? (
          <div className="text-center py-12 text-slate-400">
            <Shuffle className="w-10 h-10 mx-auto text-slate-600 mb-3" />
            <p className="text-sm font-medium">No candidate fallback pivots currently meet stability criteria.</p>
            <p className="text-xs text-slate-500 mt-1">Try expanding to sibling regions or families in your custom watchlist.</p>
          </div>
        ) : (
          <div className="space-y-4 max-h-[75vh] overflow-y-auto pr-2">
            {pivots.map((pivot, idx) => {
              const candidateKey = `${pivot.pivot_zone}-${pivot.pivot_machine_type}-${idx}`;
              const isSameZone = pivot.pivot_type === "SAME_ZONE_PIVOT";
              const isZonePivot = pivot.pivot_type === "ZONE_PIVOT";
              const isExpanded = expandedKey === candidateKey;
              const isLoading = loadingKey === candidateKey;
              const history = historyCache[candidateKey];
              const error = errorMap[candidateKey];

              const savingsPct =
                pivot.cost_savings_pct !== undefined && pivot.cost_savings_pct !== null
                  ? pivot.cost_savings_pct
                  : pivot.origin_hourly_price > 0
                  ? Number(((pivot.cost_difference / pivot.origin_hourly_price) * 100).toFixed(1))
                  : 0;

              return (
                <div
                  key={candidateKey}
                  className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 transition-all hover:border-slate-700"
                >
                  {/* Category & Reason Header */}
                  <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span
                        className={cn(
                          "px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wider font-mono flex items-center gap-1.5",
                          isSameZone
                            ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                            : isZonePivot
                            ? "bg-blue-500/20 text-blue-300 border border-blue-500/40"
                            : "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                        )}
                      >
                        {isSameZone ? (
                          <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                        ) : isZonePivot ? (
                          <MapPin className="w-3.5 h-3.5 text-blue-400" />
                        ) : (
                          <Layers className="w-3.5 h-3.5 text-purple-400" />
                        )}
                        {isSameZone
                          ? "Tier 1: Same Zone Fallback (Zero Disk Detach)"
                          : isZonePivot
                          ? "Tier 2: Sibling Zone Pivot (Same Machine)"
                          : "Tier 3: Equivalent Family Pivot (Same Cores)"}
                      </span>
                      <span className="text-xs text-slate-400 font-mono">
                        {pivot.recommendation_reason}
                      </span>
                    </div>
                  </div>

                  {/* Comparison Row */}
                  <div className="grid grid-cols-1 md:grid-cols-11 gap-3 items-center bg-slate-900/80 p-3 rounded-lg font-mono text-xs">
                    {/* Origin Pool */}
                    <div className="md:col-span-4 p-2.5 rounded bg-slate-950/80 border border-red-500/30">
                      <div className="text-[10px] text-red-400 uppercase font-bold tracking-wider mb-1">
                        Current Congested
                      </div>
                      <div className="font-bold text-slate-200">{pivot.origin_machine_type}</div>
                      <div className="text-slate-400 text-[11px]">{pivot.origin_zone}</div>
                      <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-800 text-[11px]">
                        <span className="text-red-400">Rate: {formatPercent(pivot.origin_7d_rate)}</span>
                        <span>{formatPrice(pivot.origin_hourly_price)}</span>
                      </div>
                    </div>

                    {/* Arrow / Savings */}
                    <div className="md:col-span-3 text-center py-2 flex flex-col items-center justify-center gap-1">
                      <div className="flex items-center gap-1 text-emerald-400 font-bold text-xs bg-emerald-950/60 px-2.5 py-1 rounded-full border border-emerald-800/40">
                        <TrendingDown className="w-3.5 h-3.5" />
                        -{formatPercent(pivot.preemption_savings)} Risk
                      </div>
                      <div className="text-[11px] text-slate-300 flex items-center gap-1 font-mono">
                        <DollarSign className="w-3.5 h-3.5 text-emerald-400" />
                        {pivot.cost_difference >= 0 ? (
                          <span className="text-emerald-400 font-bold">
                            Save {formatPrice(pivot.cost_difference)}{" "}
                            <span className="text-emerald-300 font-semibold">
                              (-{Math.abs(savingsPct)}% cost)
                            </span>
                          </span>
                        ) : (
                          <span className="text-slate-300 font-semibold">
                            +{formatPrice(Math.abs(pivot.cost_difference))}{" "}
                            <span className="text-rose-400">
                              (+{Math.abs(savingsPct)}% cost)
                            </span>
                          </span>
                        )}
                      </div>
                      <ArrowRight className="w-4 h-4 text-slate-500 hidden md:block mt-1" />
                    </div>

                    {/* Pivot Pool */}
                    <div className="md:col-span-4 p-2.5 rounded bg-slate-950/80 border border-emerald-500/40">
                      <div className="flex items-center justify-between gap-1 mb-1.5">
                        <div className="text-[10px] text-emerald-400 uppercase font-bold tracking-wider">
                          Recommended Pivot
                        </div>
                        <button
                          onClick={() =>
                            handleToggleInspect(
                              candidateKey,
                              pivot.region,
                              pivot.pivot_zone,
                              pivot.pivot_machine_type
                            )
                          }
                          className={cn(
                            "flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium transition-colors border",
                            isExpanded
                              ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/50 hover:bg-cyan-500/30"
                              : "bg-slate-800 hover:bg-slate-700 text-cyan-300 hover:text-cyan-200 border-slate-700"
                          )}
                          title="Inspect 30-day preemption history and pricing curve directly in this view"
                        >
                          <Eye className="w-3 h-3 text-cyan-400" />
                          <span>{isExpanded ? "Hide History" : "Inspect History"}</span>
                        </button>
                      </div>
                      <div className="font-bold text-slate-100">{pivot.pivot_machine_type}</div>
                      <div className="text-emerald-300 text-[11px]">{pivot.pivot_zone}</div>
                      <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-800 text-[11px]">
                        <span className="text-emerald-400 font-semibold">
                          Rate: {formatPercent(pivot.pivot_7d_rate)}
                        </span>
                        <div className="flex items-center gap-1.5">
                          <span>{formatPrice(pivot.pivot_hourly_price)}</span>
                          {pivot.pivot_discount_pct !== undefined && pivot.pivot_discount_pct !== null && (
                            <span
                              className={cn(
                                "text-[10px] font-bold px-1.5 py-0.5 rounded border",
                                getDiscountTierBadgeClass(getDiscountTier(pivot.pivot_discount_pct))
                              )}
                              title={
                                pivot.pivot_ondemand_price
                                  ? `${pivot.pivot_discount_pct.toFixed(1)}% savings vs on-demand list price (${formatPrice(pivot.pivot_ondemand_price)})`
                                  : `${pivot.pivot_discount_pct.toFixed(1)}% discount`
                              }
                            >
                              {pivot.pivot_discount_pct.toFixed(1)}% off on-demand
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Inline Telemetry Inspection */}
                  {isExpanded && (
                    <div className="mt-3 pt-3 border-t border-slate-800 space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Activity className="w-4 h-4 text-cyan-400" />
                          <span className="text-xs font-mono font-bold text-slate-200">
                            Telemetry History: {pivot.pivot_machine_type} ({pivot.pivot_zone})
                          </span>
                        </div>
                        {history?.severity && (
                          <span
                            className={cn(
                              "px-2 py-0.5 rounded text-[10px] font-bold uppercase font-mono border",
                              history.severity === "CRITICAL"
                                ? "bg-red-500/20 text-red-400 border-red-500/40"
                                : history.severity === "ELEVATED"
                                ? "bg-amber-500/20 text-amber-400 border-amber-500/40"
                                : "bg-emerald-500/20 text-emerald-400 border-emerald-500/40"
                            )}
                          >
                            {history.severity}
                          </span>
                        )}
                      </div>

                      {isLoading ? (
                        <div className="py-8 text-center text-slate-400 font-mono text-xs flex items-center justify-center gap-2 bg-slate-900/50 rounded-xl border border-slate-800">
                          <Loader2 className="w-4 h-4 text-cyan-400 animate-spin" />
                          <span>Fetching 30-day capacity history telemetry...</span>
                        </div>
                      ) : error ? (
                        <div className="py-4 px-4 text-center text-red-400 font-mono text-xs bg-red-950/20 border border-red-500/30 rounded-lg">
                          Failed to load telemetry: {error}
                        </div>
                      ) : history ? (
                        <div className="space-y-3">
                          {/* Quick Metrics Strip */}
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 font-mono text-xs">
                            <div className="bg-slate-900/90 p-2.5 rounded-lg border border-slate-800">
                              <div className="text-[10px] text-slate-400 mb-0.5">Recent 7d Rate</div>
                              <div className="text-base font-bold text-slate-100">
                                {formatPercent(history.recent_7d_rate)}
                              </div>
                              <div className="text-[10px] text-slate-500">
                                Baseline: {formatPercent(history.baseline_rate)}
                              </div>
                            </div>

                            <div className="bg-slate-900/90 p-2.5 rounded-lg border border-slate-800">
                              <div className="text-[10px] text-slate-400 mb-0.5">Rate Delta (&Delta;)</div>
                              <div
                                className={cn(
                                  "text-base font-bold",
                                  history.rate_delta > 0.15
                                    ? "text-red-400"
                                    : history.rate_delta > 0.05
                                    ? "text-amber-400"
                                    : "text-emerald-400"
                                )}
                              >
                                {formatSignedPercent(history.rate_delta)}
                              </div>
                              <div className="text-[10px] text-slate-500">vs 23d baseline</div>
                            </div>

                            <div className="bg-slate-900/90 p-2.5 rounded-lg border border-slate-800">
                              <div className="text-[10px] text-slate-400 mb-0.5">Regime Z-Score</div>
                              <div
                                className={cn(
                                  "text-base font-bold flex items-center gap-1",
                                  history.z_score >= 2.5
                                    ? "text-red-400"
                                    : history.z_score >= 1.8
                                    ? "text-amber-400"
                                    : "text-emerald-400"
                                )}
                              >
                                {history.z_score >= 0 ? (
                                  <TrendingUp className="w-3.5 h-3.5" />
                                ) : (
                                  <TrendingDown className="w-3.5 h-3.5" />
                                )}
                                {formatSignedZScore(history.z_score)}
                              </div>
                              <div className="text-[10px] text-slate-500">
                                {history.z_score >= 2.5
                                  ? "Severe Congestion"
                                  : history.z_score >= 1.8
                                  ? "Elevated Risk"
                                  : "Stable Baseline"}
                              </div>
                            </div>

                            <div className="bg-slate-900/90 p-2.5 rounded-lg border border-slate-800">
                              <div className="text-[10px] text-slate-400 mb-0.5 flex items-center justify-between">
                                <span>Current Spot Price</span>
                                {history.spot_discount_pct !== undefined && history.spot_discount_pct !== null && (
                                  <span
                                    className={cn(
                                      "text-[10px] font-bold px-1 py-0.2 rounded border",
                                      getDiscountTierBadgeClass(getDiscountTier(history.spot_discount_pct))
                                    )}
                                    title={
                                      history.ondemand_hourly_price
                                        ? `${history.spot_discount_pct.toFixed(1)}% savings vs on-demand (${formatPrice(history.ondemand_hourly_price)}) [${getDiscountTierLabel(getDiscountTier(history.spot_discount_pct))}]`
                                        : `${history.spot_discount_pct.toFixed(1)}% discount`
                                    }
                                  >
                                    -{history.spot_discount_pct.toFixed(0)}%
                                  </span>
                                )}
                              </div>
                              <div className="text-base font-bold text-emerald-400 flex items-center gap-0.5">
                                <DollarSign className="w-3.5 h-3.5" />
                                {formatPrice(history.current_hourly_price)}
                              </div>
                              <div className="text-[10px] text-slate-500 flex items-center justify-between">
                                <span>Billed / hr</span>
                                {history.ondemand_hourly_price !== undefined && history.ondemand_hourly_price !== null && (
                                  <span className="text-slate-400">
                                    List: {formatPrice(history.ondemand_hourly_price)}
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>

                          {/* Charts */}
                          <div className="space-y-3">
                            <PreemptionChart rates={history.rates} />
                            <PriceTimeline
                              intervals={history.intervals}
                              ondemandPrice={history.ondemand_hourly_price}
                              discountPct={history.spot_discount_pct}
                            />
                          </div>
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Footer */}
        <div className="mt-6 pt-4 border-t border-slate-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
