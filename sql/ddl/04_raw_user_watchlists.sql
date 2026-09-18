-- User-configured workload watchlists and starred pools persistent storage table
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.user_watchlists` (
  user_email STRING NOT NULL OPTIONS(description="User identity from Cloud IAP header or local dev context"),
  watchlist_type STRING NOT NULL OPTIONS(description="WORKLOAD_TARGET or STARRED_POOL"),
  target_name STRING OPTIONS(description="User-friendly workload target name"),
  region STRING NOT NULL OPTIONS(description="GCP region identifier, e.g. europe-west4"),
  zone STRING OPTIONS(description="GCP zone identifier for individual pool, e.g. europe-west4-a"),
  machine_type STRING OPTIONS(description="GCP machine type, e.g. c4d-standard-16"),
  zones_json STRING OPTIONS(description="JSON array of targeted zones, e.g. ['europe-west4-a']"),
  machine_types_json STRING OPTIONS(description="JSON array of targeted machine types"),
  custom_label STRING OPTIONS(description="Custom workload label or purpose description"),
  alert_threshold_z FLOAT64 OPTIONS(description="Custom volatility alert threshold Z-score"),
  alert_threshold_delta FLOAT64 OPTIONS(description="Custom preemption rate delta threshold"),
  is_active BOOL NOT NULL OPTIONS(description="Active state flag; false denotes soft-deleted target"),
  updated_at TIMESTAMP NOT NULL OPTIONS(description="UTC timestamp of last creation, mutation or toggle")
)
CLUSTER BY user_email, region
OPTIONS (
  description = "Persistent user-curated workload watchlists and starred pools"
);
