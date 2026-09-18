export type Severity = "CRITICAL" | "ELEVATED" | "STABLE";

export interface AnomalyItem {
  pool_key: string;
  region: string;
  zone: string;
  machine_type: string;
  family: string;
  is_watchlist: boolean;
  custom_label: string | null;
  latest_rate: number;
  recent_7d_rate: number;
  baseline_rate: number;
  rate_delta: number;
  z_score: number;
  hourly_price: number;
  ondemand_hourly_price?: number;
  spot_discount_pct?: number;
  severity: Severity;
  price_hike_detected: boolean;
  price_drop_detected?: boolean;
  price_hike_pct: number;
  price_change_pct?: number;
  pivot_count: number;
}

export interface PoolSummary {
  pool_key: string;
  region: string;
  zone: string;
  machine_type: string;
  family: string;
  is_watchlist: boolean;
  custom_label: string | null;
  latest_rate: number;
  avg_7d_rate: number;
  avg_30d_rate: number;
  hourly_price: number;
  ondemand_hourly_price?: number;
  spot_discount_pct?: number;
  severity: Severity;
  price_hike_detected?: boolean;
  price_drop_detected?: boolean;
  price_change_pct?: number;
}

export interface DailyRate {
  date: string;
  preemption_rate: number;
}

export interface PriceInterval {
  start_time: string;
  end_time: string | null;
  hourly_price: number;
  currency: string;
}

export interface PoolHistory {
  pool_key: string;
  region: string;
  zone: string;
  machine_type: string;
  family: string;
  is_watchlist: boolean;
  custom_label: string | null;
  rates: DailyRate[];
  intervals: PriceInterval[];
  latest_rate: number;
  recent_7d_rate: number;
  baseline_rate: number;
  rate_delta: number;
  z_score: number;
  severity: Severity;
  current_hourly_price: number;
  ondemand_hourly_price?: number;
  spot_discount_pct?: number;
}

export interface PivotCandidate {
  pivot_type: "SAME_ZONE_PIVOT" | "ZONE_PIVOT" | "FAMILY_PIVOT";
  priority_rank?: number;
  region: string;
  origin_zone: string;
  origin_machine_type: string;
  origin_family: string;
  origin_7d_rate: number;
  origin_hourly_price: number;
  pivot_zone: string;
  pivot_machine_type: string;
  pivot_family: string;
  pivot_7d_rate: number;
  pivot_hourly_price: number;
  pivot_ondemand_price?: number;
  pivot_discount_pct?: number;
  preemption_savings: number;
  cost_difference: number;
  cost_savings_pct?: number;
  recommendation_reason: string;
}

export interface PivotRecommendationResponse {
  pool_key: string;
  origin_severity: Severity;
  pivots: PivotCandidate[];
}

export interface WatchlistEntry {
  name?: string | null;
  region: string;
  zones: string[];
  machine_types: string[];
  alert_threshold_z?: number | null;
  alert_threshold_delta?: number | null;
}

export interface WatchlistSyncRequest {
  entries: WatchlistEntry[];
  starred_pools: string[];
  custom_labels?: Record<string, string>;
}

export interface WatchlistSyncResponse {
  status: string;
  entries: WatchlistEntry[];
  starred_pools: string[];
  custom_labels: Record<string, string>;
}
