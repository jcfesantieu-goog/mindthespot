import React, { useEffect, useState } from "react";
import { X, Activity, DollarSign, TrendingUp, TrendingDown, Shuffle } from "lucide-react";
import { PoolHistory } from "../types";
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


interface InspectorModalProps {
  isOpen: boolean;
  onClose: () => void;
  region: string;
  zone: string;
  machineType: string;
  onOpenPivots: (region: string, zone: string, machineType: string) => void;
}

export const InspectorModal: React.FC<InspectorModalProps> = ({
  isOpen,
  onClose,
  region,
  zone,
  machineType,
  onOpenPivots,
}) => {
  const [history, setHistory] = useState<PoolHistory | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !region || !zone || !machineType) return;
    setLoading(true);
    setError(null);

    fetchPoolHistory(region, zone, machineType)
      .then((data) => setHistory(data))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [isOpen, region, zone, machineType]);

  if (!isOpen) return null;

  const isCritical = history?.severity === "CRITICAL";
  const isElevated = history?.severity === "ELEVATED";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-4xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 text-slate-100">
        {/* Header */}
        <div className="flex items-start justify-between pb-4 border-b border-slate-800 mb-6">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold font-mono">{machineType}</h2>
                <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                  {region} &bull; {zone}
                </span>
                {history?.severity && (
                  <span
                    className={cn(
                      "px-2 py-0.5 rounded text-[10px] font-bold uppercase font-mono border",
                      isCritical
                        ? "bg-red-500/20 text-red-400 border-red-500/40"
                        : isElevated
                        ? "bg-amber-500/20 text-amber-400 border-amber-500/40"
                        : "bg-emerald-500/20 text-emerald-400 border-emerald-500/40"
                    )}
                  >
                    {history.severity}
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 font-mono mt-0.5">
                Detailed 30-Day Preemption Probability & 1-Year Pricing Curve
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

        {/* Content */}
        {loading ? (
          <div className="py-16 text-center text-slate-400 font-mono text-sm">
            Fetching 30-day capacity history telemetry...
          </div>
        ) : error ? (
          <div className="py-12 text-center text-red-400 font-mono text-sm">
            Failed to load telemetry: {error}
          </div>
        ) : history ? (
          <div className="space-y-6">
            {/* Quick Metrics Strip */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 font-mono text-xs">
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                <div className="text-slate-400 mb-1">Recent 7d Rate</div>
                <div className="text-lg font-bold text-slate-100">
                  {formatPercent(history.recent_7d_rate)}
                </div>
                <div className="text-[10px] text-slate-500">
                  Baseline: {formatPercent(history.baseline_rate)}
                </div>
              </div>

              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                <div className="text-slate-400 mb-1">Rate Delta (&Delta;)</div>
                <div
                  className={cn(
                    "text-lg font-bold",
                    history.rate_delta > 0.15
                      ? "text-red-400"
                      : history.rate_delta > 0.05
                      ? "text-amber-400"
                      : "text-emerald-400"
                  )}
                >
                  {formatSignedPercent(history.rate_delta)}
                </div>
                <div className="text-[10px] text-slate-500">vs 23-day baseline</div>
              </div>

              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                <div className="text-slate-400 mb-1">Regime Z-Score</div>
                <div
                  className={cn(
                    "text-lg font-bold flex items-center gap-1",
                    history.z_score >= 2.5
                      ? "text-red-400"
                      : history.z_score >= 1.8
                      ? "text-amber-400"
                      : "text-emerald-400"
                  )}
                >
                  {history.z_score >= 0 ? (
                    <TrendingUp className="w-4 h-4" />
                  ) : (
                    <TrendingDown className="w-4 h-4" />
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


              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                <div className="text-slate-400 mb-1 flex items-center justify-between">
                  <span>Current Spot Price</span>
                  {history.spot_discount_pct !== undefined && history.spot_discount_pct !== null && (
                    <span
                      className={cn(
                        "text-[10px] font-bold px-1.5 py-0.5 rounded border",
                        getDiscountTierBadgeClass(getDiscountTier(history.spot_discount_pct))
                      )}
                      title={
                        history.ondemand_hourly_price
                          ? `${history.spot_discount_pct.toFixed(1)}% savings vs on-demand (${formatPrice(history.ondemand_hourly_price)}) [${getDiscountTierLabel(getDiscountTier(history.spot_discount_pct))}]`
                          : `${history.spot_discount_pct.toFixed(1)}% discount`
                      }
                    >
                      -{history.spot_discount_pct.toFixed(1)}%
                    </span>
                  )}
                </div>
                <div className="text-lg font-bold text-emerald-400 flex items-center gap-1">
                  <DollarSign className="w-4 h-4" />
                  {formatPrice(history.current_hourly_price)}
                </div>
                <div className="text-[10px] text-slate-500 flex items-center justify-between mt-0.5">
                  <span>Billed per hour</span>
                  {history.ondemand_hourly_price !== undefined && history.ondemand_hourly_price !== null && (
                    <span className="text-slate-400">
                      On-Demand:{" "}
                      <span className="line-through decoration-slate-600">
                        {formatPrice(history.ondemand_hourly_price)}
                      </span>
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* 30-Day Preemption Chart */}
            <PreemptionChart rates={history.rates} />

            {/* Price Timeline Chart */}
            <PriceTimeline
              intervals={history.intervals}
              ondemandPrice={history.ondemand_hourly_price}
              discountPct={history.spot_discount_pct}
            />
          </div>
        ) : null}

        {/* Footer */}
        <div className="mt-6 pt-4 border-t border-slate-800 flex items-center justify-between">
          <button
            onClick={() => {
              onClose();
              onOpenPivots(region, zone, machineType);
            }}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold font-mono transition-colors"
          >
            <Shuffle className="w-4 h-4" />
            <span>Find Pivot Candidates</span>
          </button>

          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 transition-colors font-mono"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
