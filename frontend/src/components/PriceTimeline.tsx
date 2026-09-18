import React, { useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import { PriceInterval } from "../types";
import {
  formatPrice,
  cn,
  getDiscountTier,
  getDiscountTierBadgeClass,
} from "../lib/utils";

interface PriceTimelineProps {
  intervals: PriceInterval[];
  ondemandPrice?: number;
  discountPct?: number;
}

export const PriceTimeline: React.FC<PriceTimelineProps> = ({
  intervals,
  ondemandPrice,
  discountPct,
}) => {
  const [scaleMode, setScaleMode] = useState<"spot" | "ondemand">("spot");

  // Build time series steps
  const chartData = intervals.map((i) => ({
    date: i.start_time.slice(0, 10),
    price: i.hourly_price,
  }));

  // If latest interval has no end_time, append current date point to draw horizontal line
  if (intervals.length > 0) {
    const todayStr = new Date().toISOString().slice(0, 10);
    const lastPrice = intervals[intervals.length - 1].hourly_price;
    chartData.push({
      date: todayStr,
      price: lastPrice,
    });
  }

  const prices = intervals.map((i) => i.hourly_price);
  const minSpot = prices.length > 0 ? Math.min(...prices) : 0;
  const maxSpot = prices.length > 0 ? Math.max(...prices) : 1;
  const priceRange = maxSpot - minSpot;
  const spotPadding =
    priceRange > 0.0005 ? priceRange * 0.15 : Math.max(minSpot * 0.08, 0.01);

  const spotDomain = [
    Math.max(0, Number((minSpot - spotPadding).toFixed(4))),
    Number((maxSpot + spotPadding).toFixed(4)),
  ];

  const ondemandDomain = [
    Math.max(0, Math.floor(minSpot * 0.9 * 100) / 100),
    Math.ceil(Math.max(...prices, ondemandPrice || 0) * 1.08 * 100) / 100,
  ];

  const activeDomain =
    scaleMode === "ondemand" && ondemandPrice && ondemandPrice > 0
      ? ondemandDomain
      : spotDomain;

  const discountTier = getDiscountTier(discountPct);
  const badgeClass = getDiscountTierBadgeClass(discountTier);

  return (
    <div className="w-full h-56 bg-slate-950/70 p-4 rounded-xl border border-slate-800 flex flex-col justify-between">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono">
            Historical Spot Hourly Pricing Timeline
          </h4>
          {/* Scale mode toggle */}
          {ondemandPrice && ondemandPrice > 0 && (
            <div className="inline-flex rounded-md p-0.5 bg-slate-900 border border-slate-800 text-[10px] font-mono">
              <button
                type="button"
                onClick={() => setScaleMode("spot")}
                className={cn(
                  "px-2 py-0.5 rounded transition-all font-medium",
                  scaleMode === "spot"
                    ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                    : "text-slate-400 hover:text-slate-200"
                )}
                title="Focus Y-axis strictly on Spot price dynamics to highlight price hikes and drops"
              >
                Focus Spot
              </button>
              <button
                type="button"
                onClick={() => setScaleMode("ondemand")}
                className={cn(
                  "px-2 py-0.5 rounded transition-all font-medium",
                  scaleMode === "ondemand"
                    ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                    : "text-slate-400 hover:text-slate-200"
                )}
                title="Scale Y-axis to include On-Demand ceiling list price"
              >
                Full Scale
              </button>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {discountPct !== undefined && discountPct !== null && (
            <span
              className={cn(
                "text-[11px] font-mono font-semibold px-2 py-0.5 rounded border",
                badgeClass
              )}
            >
              {discountPct.toFixed(1)}% off on-demand
            </span>
          )}
          <span className="text-xs font-mono text-slate-300 font-medium">
            Spot:{" "}
            <span className="text-emerald-400 font-bold">
              {formatPrice(intervals[intervals.length - 1]?.hourly_price || 0)}
            </span>
          </span>
          {ondemandPrice !== undefined && ondemandPrice !== null && (
            <span className="text-xs font-mono text-slate-400">
              (On-Demand:{" "}
              <span className="line-through decoration-slate-500">
                {formatPrice(ondemandPrice)}
              </span>
              )
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 w-full min-h-[140px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis
              dataKey="date"
              stroke="#64748b"
              tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }}
              tickLine={false}
            />
            <YAxis
              stroke="#64748b"
              tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }}
              domain={activeDomain}
              tickFormatter={(v) => `$${v.toFixed(3)}`}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#0f172a",
                borderColor: "#334155",
                borderRadius: "0.5rem",
                fontSize: "12px",
                fontFamily: "JetBrains Mono",
                color: "#f8fafc",
              }}
              formatter={(val: any) => [formatPrice(Number(val)), "Spot Hourly Price"]}
            />
            {scaleMode === "ondemand" && ondemandPrice && ondemandPrice > 0 && (
              <ReferenceLine
                y={ondemandPrice}
                stroke="#64748b"
                strokeDasharray="4 4"
                label={{
                  value: `On-Demand: ${formatPrice(ondemandPrice)}`,
                  fill: "#94a3b8",
                  fontSize: 10,
                  fontFamily: "JetBrains Mono",
                  position: "insideTopRight",
                }}
              />
            )}
            <Line
              type="stepAfter"
              dataKey="price"
              stroke="#10b981"
              strokeWidth={2}
              dot={{ r: 3, fill: "#10b981" }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

