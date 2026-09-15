import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPercent(val: number): string {
  return `${(val * 100).toFixed(1)}%`;
}

export function formatPrice(val: number): string {
  return `$${val.toFixed(4)}/hr`;
}
