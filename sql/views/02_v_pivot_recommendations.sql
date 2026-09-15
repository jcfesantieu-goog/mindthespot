-- View: v_pivot_recommendations
-- Identifies fallback candidate pools (sibling zones and equivalent families) for congested pools.

CREATE OR REPLACE VIEW `{project}.{dataset}.v_pivot_recommendations` AS
WITH active_shifts AS (
  SELECT *
  FROM `{project}.{dataset}.v_regime_shifts`
),

candidate_pools AS (
  SELECT *
  FROM `{project}.{dataset}.v_regime_shifts`
  WHERE severity = 'STABLE'
    AND recent_7d_rate <= 0.10
)

-- 1. Sibling Zone Pivots (same machine type, different zone in same region)
SELECT
  a.region,
  a.zone AS origin_zone,
  a.machine_type AS origin_machine_type,
  a.family AS origin_family,
  a.severity AS origin_severity,
  a.recent_7d_rate AS origin_7d_rate,
  a.hourly_price AS origin_hourly_price,
  'ZONE_PIVOT' AS pivot_type,
  c.zone AS pivot_zone,
  c.machine_type AS pivot_machine_type,
  c.family AS pivot_family,
  c.recent_7d_rate AS pivot_7d_rate,
  c.hourly_price AS pivot_hourly_price,
  ROUND(a.recent_7d_rate - c.recent_7d_rate, 4) AS preemption_savings,
  ROUND(a.hourly_price - c.hourly_price, 4) AS cost_difference,
  'Sibling zone with stable preemption profile' AS recommendation_reason
FROM active_shifts a
INNER JOIN candidate_pools c
  ON a.region = c.region
 AND a.machine_type = c.machine_type
 AND a.zone != c.zone
WHERE a.severity IN ('CRITICAL', 'ELEVATED')

UNION ALL

-- 2. Equivalent Family Pivots (different family with compatible architecture in same region)
SELECT
  a.region,
  a.zone AS origin_zone,
  a.machine_type AS origin_machine_type,
  a.family AS origin_family,
  a.severity AS origin_severity,
  a.recent_7d_rate AS origin_7d_rate,
  a.hourly_price AS origin_hourly_price,
  'FAMILY_PIVOT' AS pivot_type,
  c.zone AS pivot_zone,
  c.machine_type AS pivot_machine_type,
  c.family AS pivot_family,
  c.recent_7d_rate AS pivot_7d_rate,
  c.hourly_price AS pivot_hourly_price,
  ROUND(a.recent_7d_rate - c.recent_7d_rate, 4) AS preemption_savings,
  ROUND(a.hourly_price - c.hourly_price, 4) AS cost_difference,
  'Equivalent compute architecture with lower preemption risk' AS recommendation_reason
FROM active_shifts a
INNER JOIN candidate_pools c
  ON a.region = c.region
 AND a.family != c.family
 AND (
   -- Compute-Optimized AMD / Arm / Intel equivalents
   (a.family = 'c4d' AND c.family IN ('c3d', 'c4a', 'n2d'))
   OR (a.family = 'c3d' AND c.family IN ('c4d', 'c4a', 'n2d'))
   OR (a.family = 'c4a' AND c.family IN ('c4d', 'c3d', 'n2d'))
   OR (a.family = 'c3'  AND c.family IN ('c2', 'c4d', 'c3d'))
   OR (a.family = 'c2'  AND c.family IN ('c3', 'c4d', 'c3d'))
   -- General Purpose equivalents
   OR (a.family = 'n2d' AND c.family IN ('n2', 'e2', 'c3d'))
   OR (a.family = 'n2'  AND c.family IN ('n2d', 'e2', 'c3'))
   OR (a.family = 'e2'  AND c.family IN ('n2d', 'n2'))
 )
WHERE a.severity IN ('CRITICAL', 'ELEVATED');
