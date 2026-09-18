-- View: v_regime_shifts
-- Computes rolling 7d vs 23d baseline Z-score and flags price hikes for active Spot pools.

CREATE OR REPLACE VIEW `{project}.{dataset}.v_regime_shifts` AS
WITH latest_snapshot AS (
  SELECT MAX(snapshot_date) AS max_snapshot_date
  FROM `{project}.{dataset}.preemption_history`
),

deduped_preemption AS (
  SELECT
    p.snapshot_date,
    p.region,
    p.zone,
    p.machine_type,
    p.family,
    p.telemetry_date,
    p.preemption_rate,
    p.is_watchlist,
    p.custom_label,
    ROW_NUMBER() OVER (
      PARTITION BY p.region, p.zone, p.machine_type, p.telemetry_date
      ORDER BY p.crawled_at DESC
    ) AS dedup_rank
  FROM `{project}.{dataset}.preemption_history` p
  INNER JOIN latest_snapshot s ON p.snapshot_date = s.max_snapshot_date
),

ranked_preemption AS (
  SELECT
    snapshot_date,
    region,
    zone,
    machine_type,
    family,
    telemetry_date,
    preemption_rate,
    is_watchlist,
    custom_label,
    ROW_NUMBER() OVER (
      PARTITION BY region, zone, machine_type
      ORDER BY telemetry_date DESC
    ) AS day_rank_desc
  FROM deduped_preemption
  WHERE dedup_rank = 1
),

pool_windows AS (
  SELECT
    region,
    zone,
    machine_type,
    family,
    ANY_VALUE(is_watchlist) AS is_watchlist,
    ANY_VALUE(custom_label) AS custom_label,
    -- Latest 7 days (rank 1 to 7)
    AVG(CASE WHEN day_rank_desc <= 7 THEN preemption_rate END) AS mean_recent_7d,
    -- 23 days baseline (rank 8 to 30)
    AVG(CASE WHEN day_rank_desc > 7 AND day_rank_desc <= 30 THEN preemption_rate END) AS mean_baseline_23d,
    STDDEV_SAMP(CASE WHEN day_rank_desc > 7 AND day_rank_desc <= 30 THEN preemption_rate END) AS stddev_baseline_23d,
    -- Latest single-day rate
    MAX(CASE WHEN day_rank_desc = 1 THEN preemption_rate END) AS latest_day_rate
  FROM ranked_preemption
  GROUP BY region, zone, machine_type, family
),

z_scored AS (
  SELECT
    region,
    zone,
    machine_type,
    family,
    is_watchlist,
    custom_label,
    ROUND(latest_day_rate, 4) AS latest_rate,
    ROUND(COALESCE(mean_recent_7d, 0.0), 4) AS recent_7d_rate,
    ROUND(COALESCE(mean_baseline_23d, 0.0), 4) AS baseline_rate,
    ROUND(COALESCE(mean_recent_7d, 0.0) - COALESCE(mean_baseline_23d, 0.0), 4) AS rate_delta,
    ROUND(
      (COALESCE(mean_recent_7d, 0.0) - COALESCE(mean_baseline_23d, 0.0)) /
      GREATEST(COALESCE(stddev_baseline_23d, 0.02), 0.02),
      2
    ) AS z_score
  FROM pool_windows
),

deduped_prices AS (
  SELECT
    pr.region,
    pr.machine_type,
    pr.hourly_price,
    pr.currency,
    pr.interval_start,
    ROW_NUMBER() OVER (
      PARTITION BY pr.region, pr.machine_type, pr.interval_start
      ORDER BY pr.crawled_at DESC
    ) AS dedup_rank
  FROM `{project}.{dataset}.price_history` pr
  INNER JOIN latest_snapshot s ON pr.snapshot_date = s.max_snapshot_date
),

ranked_prices AS (
  SELECT
    region,
    machine_type,
    hourly_price,
    currency,
    ROW_NUMBER() OVER (
      PARTITION BY region, machine_type
      ORDER BY interval_start DESC
    ) AS price_rank_desc
  FROM deduped_prices
  WHERE dedup_rank = 1
),

latest_prices AS (
  SELECT region, machine_type, hourly_price, currency
  FROM ranked_prices
  WHERE price_rank_desc = 1
),

previous_prices AS (
  SELECT region, machine_type, hourly_price AS prev_hourly_price
  FROM ranked_prices
  WHERE price_rank_desc = 2
)

SELECT
  z.region,
  z.zone,
  z.machine_type,
  z.family,
  z.is_watchlist,
  z.custom_label,
  z.latest_rate,
  z.recent_7d_rate,
  z.baseline_rate,
  z.rate_delta,
  z.z_score,
  lp.hourly_price,
  lp.currency,
  od.hourly_price AS ondemand_hourly_price,
  ROUND(
    ((od.hourly_price - lp.hourly_price) / NULLIF(od.hourly_price, 0)) * 100.0,
    1
  ) AS spot_discount_pct,
  ROUND(
    ((lp.hourly_price - pp.prev_hourly_price) / NULLIF(pp.prev_hourly_price, 0)) * 100.0,
    2
  ) AS price_change_pct,
  CASE
    WHEN pp.prev_hourly_price IS NOT NULL AND lp.hourly_price > pp.prev_hourly_price * 1.05 THEN TRUE
    ELSE FALSE
  END AS price_hike_detected,
  CASE
    WHEN pp.prev_hourly_price IS NOT NULL AND lp.hourly_price < pp.prev_hourly_price * 0.95 THEN TRUE
    ELSE FALSE
  END AS price_drop_detected,
  CASE
    WHEN (z.z_score >= 2.5 AND z.recent_7d_rate >= 0.20)
      OR (z.rate_delta >= 0.25)
      OR (z.recent_7d_rate >= 0.50) THEN 'CRITICAL'
    WHEN (z.z_score >= 1.8 AND z.recent_7d_rate >= 0.15)
      OR (z.rate_delta >= 0.15) THEN 'ELEVATED'
    ELSE 'STABLE'
  END AS severity
FROM z_scored z
LEFT JOIN latest_prices lp ON z.region = lp.region AND z.machine_type = lp.machine_type
LEFT JOIN previous_prices pp ON z.region = pp.region AND z.machine_type = pp.machine_type
LEFT JOIN `{project}.{dataset}.on_demand_pricing` od ON z.region = od.region AND z.machine_type = od.machine_type;

