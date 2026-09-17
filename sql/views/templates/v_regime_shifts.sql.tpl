WITH latest_snapshot AS (
  SELECT MAX(snapshot_date) AS max_snapshot_date
  FROM `${project}.${dataset_raw}.preemption_history`
),

ranked_preemption AS (
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
      PARTITION BY p.region, p.zone, p.machine_type
      ORDER BY p.telemetry_date DESC
    ) AS day_rank_desc
  FROM `${project}.${dataset_raw}.preemption_history` p
  INNER JOIN latest_snapshot s ON p.snapshot_date = s.max_snapshot_date
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
    -- Baseline standard deviation
    STDDEV_SAMP(CASE WHEN day_rank_desc > 7 AND day_rank_desc <= 30 THEN preemption_rate END) AS std_baseline_23d,
    COUNT(CASE WHEN day_rank_desc <= 7 THEN 1 END) AS count_recent_7d,
    COUNT(CASE WHEN day_rank_desc > 7 AND day_rank_desc <= 30 THEN 1 END) AS count_baseline_23d
  FROM ranked_preemption
  GROUP BY region, zone, machine_type, family
),

ranked_prices AS (
  SELECT
    pr.region,
    pr.machine_type,
    pr.hourly_price,
    pr.currency,
    ROW_NUMBER() OVER (
      PARTITION BY pr.region, pr.machine_type
      ORDER BY pr.interval_start DESC
    ) AS price_rank_desc
  FROM `${project}.${dataset_raw}.price_history` pr
  INNER JOIN latest_snapshot s ON pr.snapshot_date = s.max_snapshot_date
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
  w.region,
  w.zone,
  w.machine_type,
  w.family,
  w.is_watchlist,
  w.custom_label,
  ROUND(w.mean_recent_7d, 4) AS recent_7d_rate,
  ROUND(w.mean_baseline_23d, 4) AS baseline_rate,
  ROUND(w.mean_recent_7d - w.mean_baseline_23d, 4) AS rate_delta,
  -- Z-score calculation with 0.02 noise floor
  ROUND(
    (w.mean_recent_7d - w.mean_baseline_23d) / GREATEST(COALESCE(w.std_baseline_23d, 0.02), 0.02),
    2
  ) AS z_score,
  lp.hourly_price,
  lp.currency,
  CASE
    WHEN pp.prev_hourly_price IS NOT NULL AND lp.hourly_price > pp.prev_hourly_price * 1.10 THEN TRUE
    ELSE FALSE
  END AS price_hike_detected,
  CASE
    WHEN (
      ((w.mean_recent_7d - w.mean_baseline_23d) / GREATEST(COALESCE(w.std_baseline_23d, 0.02), 0.02) >= 2.5 AND w.mean_recent_7d >= 0.20)
      OR (w.mean_recent_7d - w.mean_baseline_23d >= 0.25)
      OR (w.mean_recent_7d >= 0.50)
    ) THEN 'CRITICAL'
    WHEN (
      ((w.mean_recent_7d - w.mean_baseline_23d) / GREATEST(COALESCE(w.std_baseline_23d, 0.02), 0.02) >= 1.8 AND w.mean_recent_7d >= 0.15)
      OR (w.mean_recent_7d - w.mean_baseline_23d >= 0.15)
    ) THEN 'ELEVATED'
    ELSE 'STABLE'
  END AS severity
FROM pool_windows w
LEFT JOIN latest_prices lp ON w.region = lp.region AND w.machine_type = lp.machine_type
LEFT JOIN previous_prices pp ON w.region = pp.region AND w.machine_type = pp.machine_type

