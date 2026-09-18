import React from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  TrendingUp,
  DollarSign,
  Shuffle,
  Star,
  HelpCircle,
} from "lucide-react";
import { AnomalyItem } from "../types";
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


interface AnomalyCardProps {
  anomaly: AnomalyItem;
  onInspect: (anomaly: AnomalyItem) => void;
  onViewPivots: (anomaly: AnomalyItem) => void;
}

export const AnomalyCard: React.FC<AnomalyCardProps> = ({
  anomaly,
  onInspect,
  onViewPivots,
}) => {
  const isCritical = anomaly.severity === "CRITICAL";

  return (
    <div
      className={cn(
        "rounded-xl border p-5 transition-all duration-200 hover:shadow-lg relative overflow-hidden backdrop-blur-sm",
        isCritical
          ? "border-red-500/40 bg-red-950/15 hover:border-red-500/70"
          : "border-amber-500/40 bg-amber-950/15 hover:border-amber-500/70"
      )}
    >
      {/* Top Banner Accent */}
      <div
        className={cn(
          "absolute top-0 left-0 right-0 h-1",
          isCritical ? "bg-red-500" : "bg-amber-500"
        )}
      />

      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <h3 className="font-mono text-base font-bold text-slate-100 tracking-tight">
              {anomaly.machine_type}
            </h3>
            <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700 font-mono">
              {anomaly.family.toUpperCase()}
            </span>
            {anomaly.is_watchlist && (
              <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 font-medium">
                <Star className="w-3 h-3 fill-amber-400" />
                {anomaly.custom_label || "Watchlist"}
              </span>
            )}
          </div>
          <p className="text-xs text-slate-400 font-mono">
            {anomaly.region} &bull; <span className="text-slate-300 font-semibold">{anomaly.zone}</span>
          </p>
        </div>

        {/* Severity Badge */}
        <div
          className={cn(
            "flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wider border",
            isCritical
              ? "bg-red-500/20 text-red-400 border-red-500/50"
              : "bg-amber-500/20 text-amber-400 border-amber-500/50"
          )}
        >
          <AlertTriangle className="w-3.5 h-3.5" />
          {anomaly.severity}
        </div>
      </div>

      {/* Metric Cards Grid */}
      <div className="grid grid-cols-2 gap-2 mb-4 text-xs">
        <div className="bg-slate-900/60 rounded-lg p-2.5 border border-slate-800/80">
          <div className="text-slate-400 mb-1 flex items-center justify-between">
            <span>7d Recent Avg</span>
            <span className={cn("font-bold font-mono", isCritical ? "text-red-400" : "text-amber-400")}>
              {formatSignedPercent(anomaly.rate_delta)}
            </span>
          </div>
          <div className="text-lg font-bold text-slate-100 font-mono">
            {formatPercent(anomaly.recent_7d_rate)}
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">
            Baseline: {formatPercent(anomaly.baseline_rate)}
          </div>
        </div>

        <div
          className="bg-slate-900/60 rounded-lg p-2.5 border border-slate-800/80 cursor-help group relative"
          title={
            anomaly.z_score >= 2.5
              ? "Critical Shift (Z ≥ 2.5σ): Extreme eviction surge (>2.5 std dev over 23d baseline). Probability < 0.6% in normal conditions."
              : "Elevated Risk (Z ≥ 1.8σ): Statistically significant upward preemption drift (>1.8 std dev). Probability < 3.6%."
          }
        >
          <div className="text-slate-400 mb-1 flex items-center justify-between">
            <span className="flex items-center gap-1">
              <span>Z-Score Shift</span>
              <HelpCircle className="w-3 h-3 text-slate-500 group-hover:text-cyan-400 transition-colors" />
            </span>
            <TrendingUp className="w-3.5 h-3.5 text-red-400" />
          </div>
          <div className="text-lg font-bold text-slate-100 font-mono">
            {formatSignedZScore(anomaly.z_score)}
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">
            {anomaly.z_score >= 2.5
              ? "Critical Surge (p < 0.6%)"
              : anomaly.z_score >= 1.8
              ? "Elevated Risk (p < 3.6%)"
              : "Moderate Shift"}
          </div>
        </div>

      </div>

      {/* Price & Spot Discount / Price Hike / Drop indicator */}
      <div className="flex items-center justify-between text-xs py-2 px-3 rounded-lg bg-slate-900/40 border border-slate-800/60 mb-4 font-mono">
        <div className="flex items-center gap-1.5 text-slate-300">
          <DollarSign className="w-3.5 h-3.5 text-slate-400" />
          <span>Spot:</span>
          <span className="font-bold text-slate-100">{formatPrice(anomaly.hourly_price)}</span>
          {anomaly.ondemand_hourly_price !== undefined && anomaly.ondemand_hourly_price !== null && (
            <span
              className="text-[11px] text-slate-500 line-through decoration-slate-600 ml-1"
              title={`Public On-Demand Price: ${formatPrice(anomaly.ondemand_hourly_price)}`}
            >
              {formatPrice(anomaly.ondemand_hourly_price)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {anomaly.spot_discount_pct !== undefined && anomaly.spot_discount_pct !== null && (
            <span
              className={cn(
                "text-[11px] font-bold px-2 py-0.5 rounded border",
                getDiscountTierBadgeClass(getDiscountTier(anomaly.spot_discount_pct))
              )}
              title={
                anomaly.ondemand_hourly_price
                  ? `${anomaly.spot_discount_pct.toFixed(1)}% savings compared to public on-demand (${formatPrice(anomaly.ondemand_hourly_price)}) [${getDiscountTierLabel(getDiscountTier(anomaly.spot_discount_pct))}]`
                  : `${anomaly.spot_discount_pct.toFixed(1)}% discount`
              }
            >
              -{anomaly.spot_discount_pct.toFixed(1)}%
            </span>
          )}
          {anomaly.price_hike_detected && (
            <span className="flex items-center gap-1 text-[11px] text-rose-300 font-semibold bg-rose-950/60 px-2 py-0.5 rounded border border-rose-800/40">
              <ArrowUpRight className="w-3 h-3 text-rose-400" />
              {anomaly.price_change_pct
                ? `${anomaly.price_change_pct > 0 ? "+" : ""}${anomaly.price_change_pct.toFixed(1)}% Hike`
                : `+${(anomaly.price_hike_pct * 100).toFixed(0)}% Hike`}
            </span>
          )}
          {anomaly.price_drop_detected && (
            <span className="flex items-center gap-1 text-[11px] text-emerald-300 font-semibold bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800/40">
              <ArrowDownRight className="w-3 h-3 text-emerald-400" />
              {anomaly.price_change_pct
                ? `${anomaly.price_change_pct.toFixed(1)}% Drop`
                : "-5.0% Drop"}
            </span>
          )}
        </div>
      </div>

      {/* Card Actions */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => onInspect(anomaly)}
          className="flex-1 text-xs py-2 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors font-medium border border-slate-700/60 text-center"
        >
          Inspect 30d History
        </button>
        <button
          onClick={() => onViewPivots(anomaly)}
          className={cn(
            "flex items-center justify-center gap-1.5 text-xs py-2 px-3 rounded-lg font-semibold transition-all",
            anomaly.pivot_count > 0
              ? "bg-cyan-600 hover:bg-cyan-500 text-white shadow-sm shadow-cyan-900/30"
              : "bg-slate-800 text-slate-400 cursor-not-allowed border border-slate-700"
          )}
          disabled={anomaly.pivot_count === 0}
        >
          <Shuffle className="w-3.5 h-3.5" />
          {anomaly.pivot_count > 0 ? `Pivots (${anomaly.pivot_count})` : "No Pivots"}
        </button>
      </div>
    </div>
  );
};
