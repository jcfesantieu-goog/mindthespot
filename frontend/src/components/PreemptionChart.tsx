import React from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  CartesianGrid,
} from "recharts";
import { DailyRate } from "../types";
import { formatPercent } from "../lib/utils";

interface PreemptionChartProps {
  rates: DailyRate[];
}

export const PreemptionChart: React.FC<PreemptionChartProps> = ({ rates }) => {
  const chartData = rates.map((r) => ({
    date: r.date.slice(5), // MM-DD
    rate: r.preemption_rate,
    percentage: (r.preemption_rate * 100).toFixed(1),
  }));

  const maxRate = Math.max(...rates.map((r) => r.preemption_rate), 0.3);
  const yDomainMax = Math.min(1.0, Math.ceil((maxRate + 0.05) * 10) / 10);

  return (
    <div className="w-full h-64 bg-slate-950/70 p-4 rounded-xl border border-slate-800">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono">
          30-Day Rolling Preemption Probability History
        </h4>
        <div className="flex items-center gap-4 text-xs font-mono">
          <span className="flex items-center gap-1.5 text-amber-400">
            <span className="w-2.5 h-0.5 bg-amber-400 inline-block" /> 20% Warning
          </span>
          <span className="flex items-center gap-1.5 text-red-400">
            <span className="w-2.5 h-0.5 bg-red-400 inline-block" /> 50% Critical
          </span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height="85%">
        <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="preemptGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#ef4444" stopOpacity={0.6} />
              <stop offset="95%" stopColor="#ef4444" stopOpacity={0.0} />
            </linearGradient>
          </defs>
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
            domain={[0, yDomainMax]}
            tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
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
            formatter={(val: any) => [formatPercent(Number(val)), "Preemption Rate"]}
          />
          <ReferenceLine
            y={0.2}
            stroke="#f59e0b"
            strokeDasharray="4 4"
            strokeWidth={1.5}
          />
          <ReferenceLine
            y={0.5}
            stroke="#ef4444"
            strokeDasharray="4 4"
            strokeWidth={1.5}
          />
          <Area
            type="monotone"
            dataKey="rate"
            stroke="#ef4444"
            strokeWidth={2}
            fillOpacity={1}
            fill="url(#preemptGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};
