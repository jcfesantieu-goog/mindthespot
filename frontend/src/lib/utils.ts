import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPercent(val: number): string {
  return `${(val * 100).toFixed(1)}%`;
}

export function formatSignedPercent(val: number): string {
  const formatted = `${(Math.abs(val) * 100).toFixed(1)}%`;
  if (val > 0) return `+${formatted}`;
  if (val < 0) return `-${formatted}`;
  return `0.0%`;
}

export function formatSignedZScore(val: number): string {
  const formatted = Math.abs(val).toFixed(2);
  if (val > 0) return `+${formatted}σ`;
  if (val < 0) return `-${formatted}σ`;
  return `0.00σ`;
}

export function formatPrice(val: number): string {
  return `$${val.toFixed(4)}/hr`;
}

export function formatDiscount(val?: number | null): string {
  if (val === undefined || val === null) return "--";
  return `${val.toFixed(1)}% off`;
}

export type DiscountTier = "great" | "good" | "low" | "none";

export function getDiscountTier(val?: number | null): DiscountTier {
  if (val === undefined || val === null) return "none";
  if (val > 80.0) return "great";
  if (val >= 50.0) return "good";
  return "low";
}

export function getDiscountTierLabel(tier: DiscountTier): string {
  switch (tier) {
    case "great":
      return "Deep Discount (>80%)";
    case "good":
      return "Standard Discount (50-80%)";
    case "low":
      return "Low Discount (<50%)";
    case "none":
      return "Unknown";
  }
}

export function getDiscountTierBadgeClass(tier: DiscountTier): string {
  switch (tier) {
    case "great":
      return "bg-emerald-500/20 text-emerald-300 border-emerald-500/40";
    case "good":
      return "bg-cyan-500/20 text-cyan-300 border-cyan-500/40";
    case "low":
      return "bg-amber-500/20 text-amber-300 border-amber-500/40";
    case "none":
      return "bg-slate-800 text-slate-400 border-slate-700";
  }
}


