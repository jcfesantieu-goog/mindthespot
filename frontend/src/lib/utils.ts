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


