import React, { useState } from "react";
import {
  X,
  Shuffle,
  ArrowRight,
  Check,
  Copy,
  Layers,
  MapPin,
  TrendingDown,
  DollarSign,
} from "lucide-react";
import { PivotCandidate } from "../types";
import { cn, formatPercent, formatPrice } from "../lib/utils";

interface PivotModalProps {
  isOpen: boolean;
  onClose: () => void;
  poolKey: string;
  pivots: PivotCandidate[];
}

export const PivotModal: React.FC<PivotModalProps> = ({
  isOpen,
  onClose,
  poolKey,
  pivots,
}) => {
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  if (!isOpen) return null;

  const handleCopy = (pivot: PivotCandidate, index: number) => {
    const snippet = `# Fallback pivot for ${pivot.origin_machine_type} (${pivot.origin_zone})
gcloud compute instances create spot-worker-${pivot.pivot_family} \\
    --zone=${pivot.pivot_zone} \\
    --machine-type=${pivot.pivot_machine_type} \\
    --provisioning-model=SPOT \\
    --instance-termination-action=STOP`;

    navigator.clipboard.writeText(snippet);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-4xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 text-slate-100">
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
            <p className="text-xs text-slate-500 mt-1">Try expanding to sibling regions in your custom watchlist.</p>
          </div>
        ) : (
          <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-1">
            {pivots.map((pivot, idx) => {
              const isZonePivot = pivot.pivot_type === "ZONE_PIVOT";

              return (
                <div
                  key={`${pivot.pivot_zone}-${pivot.pivot_machine_type}-${idx}`}
                  className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 transition-all hover:border-slate-700"
                >
                  <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          "px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wider font-mono flex items-center gap-1",
                          isZonePivot
                            ? "bg-blue-500/20 text-blue-400 border border-blue-500/40"
                            : "bg-purple-500/20 text-purple-400 border border-purple-500/40"
                        )}
                      >
                        {isZonePivot ? <MapPin className="w-3 h-3" /> : <Layers className="w-3 h-3" />}
                        {isZonePivot ? "Sibling Zone Pivot" : "Equivalent Family Pivot"}
                      </span>
                      <span className="text-xs text-slate-400">
                        {pivot.recommendation_reason}
                      </span>
                    </div>

                    <button
                      onClick={() => handleCopy(pivot, idx)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-mono font-medium text-slate-200 transition-colors border border-slate-700"
                    >
                      {copiedIndex === idx ? (
                        <>
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                          <span>Copied Snippet!</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3.5 h-3.5 text-slate-400" />
                          <span>Copy gcloud Run</span>
                        </>
                      )}
                    </button>
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
                      <div className="text-[10px] text-slate-400 flex items-center gap-1">
                        <DollarSign className="w-3 h-3 text-emerald-400" />
                        {pivot.cost_difference >= 0 ? (
                          <span className="text-emerald-400">
                            Save {formatPrice(pivot.cost_difference)}
                          </span>
                        ) : (
                          <span className="text-slate-300">
                            +{formatPrice(Math.abs(pivot.cost_difference))}
                          </span>
                        )}
                      </div>
                      <ArrowRight className="w-4 h-4 text-slate-500 hidden md:block mt-1" />
                    </div>

                    {/* Pivot Pool */}
                    <div className="md:col-span-4 p-2.5 rounded bg-slate-950/80 border border-emerald-500/40">
                      <div className="text-[10px] text-emerald-400 uppercase font-bold tracking-wider mb-1">
                        Recommended Pivot
                      </div>
                      <div className="font-bold text-slate-100">{pivot.pivot_machine_type}</div>
                      <div className="text-emerald-300 text-[11px]">{pivot.pivot_zone}</div>
                      <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-800 text-[11px]">
                        <span className="text-emerald-400 font-semibold">
                          Rate: {formatPercent(pivot.pivot_7d_rate)}
                        </span>
                        <span>{formatPrice(pivot.pivot_hourly_price)}</span>
                      </div>
                    </div>
                  </div>
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
