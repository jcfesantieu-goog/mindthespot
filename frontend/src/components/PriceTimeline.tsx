import React from "react";
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
import { formatPrice } from "../lib/utils";

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
  const minPrice = prices.length > 0 ? Math.min(...prices) : 0;
  const maxPrice =
    ondemandPrice && ondemandPrice > 0
      ? Math.max(...prices, ondemandPrice)
      : prices.length > 0
      ? Math.max(...prices)
      : 1;

  const yDomain = [
    Math.max(0, Math.floor(minPrice * 0.9 * 100) / 100),
    Math.ceil(maxPrice * 1.08 * 100) / 100,
  ];

  return (
    <div className="w-full h-52 bg-slate-950/70 p-4 rounded-xl border border-slate-800">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono">
          Historical Spot Hourly Pricing Timeline
        </h4>
        <div className="flex items-center gap-2">
          {discountPct !== undefined && discountPct !== null && (
            <span className="text-[11px] font-mono text-emerald-400 font-semibold bg-emerald-950/80 border border-emerald-800/50 px-2 py-0.5 rounded">
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

      <ResponsiveContainer width="100%" height="80%">
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
            domain={yDomain}
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
          {ondemandPrice && ondemandPrice > 0 && (
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
  );
};
