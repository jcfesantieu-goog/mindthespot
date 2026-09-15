-- Raw spot preemption rate telemetry partitioned daily and clustered by pool keys
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.preemption_history` (
  snapshot_date DATE NOT NULL OPTIONS(description="Date of crawl execution snapshot"),
  crawled_at TIMESTAMP NOT NULL OPTIONS(description="UTC timestamp of crawl execution"),
  region STRING NOT NULL OPTIONS(description="GCP region identifier, e.g. europe-west4"),
  zone STRING NOT NULL OPTIONS(description="GCP zone identifier, e.g. europe-west4-a"),
  machine_type STRING NOT NULL OPTIONS(description="GCP machine type, e.g. c4d-standard-16"),
  family STRING NOT NULL OPTIONS(description="Machine family prefix, e.g. c4d"),
  telemetry_date DATE NOT NULL OPTIONS(description="Date of historical observation YYYY-MM-DD"),
  preemption_rate FLOAT64 NOT NULL OPTIONS(description="Preemption rate between 0.0 and 1.0"),
  is_watchlist BOOL OPTIONS(description="Flag indicating user watchlist inclusion"),
  custom_label STRING OPTIONS(description="Optional custom team/workload label")
)
PARTITION BY snapshot_date
CLUSTER BY region, zone, machine_type
OPTIONS (
  description = "Daily snapshot partitions of 30-day GCP Spot preemption rate history"
);
