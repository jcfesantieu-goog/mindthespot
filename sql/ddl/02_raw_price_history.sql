-- Raw spot price intervals partitioned daily and clustered by region & machine type
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.price_history` (
  snapshot_date DATE NOT NULL OPTIONS(description="Date of crawl execution snapshot"),
  crawled_at TIMESTAMP NOT NULL OPTIONS(description="UTC timestamp of crawl execution"),
  region STRING NOT NULL OPTIONS(description="GCP region identifier, e.g. europe-west4"),
  machine_type STRING NOT NULL OPTIONS(description="GCP machine type, e.g. c4d-standard-16"),
  family STRING NOT NULL OPTIONS(description="Machine family prefix, e.g. c4d"),
  interval_start TIMESTAMP NOT NULL OPTIONS(description="Start timestamp of price interval"),
  interval_end TIMESTAMP OPTIONS(description="End timestamp of price interval or NULL if currently active"),
  hourly_price FLOAT64 NOT NULL OPTIONS(description="Price in currency per hour"),
  currency STRING NOT NULL OPTIONS(description="Currency code, e.g. USD")
)
PARTITION BY snapshot_date
CLUSTER BY region, machine_type
OPTIONS (
  description = "Daily snapshot partitions of 1-year GCP Spot interval pricing history"
);
