-- GCP Compute Engine public on-demand list pricing reference table
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.on_demand_pricing` (
  region STRING NOT NULL OPTIONS(description="GCP region identifier, e.g. europe-west1"),
  machine_type STRING NOT NULL OPTIONS(description="GCP machine type, e.g. c4a-standard-16"),
  family STRING NOT NULL OPTIONS(description="Machine family prefix, e.g. c4a"),
  vcpus INT64 NOT NULL OPTIONS(description="Number of guest vCPUs"),
  memory_gb FLOAT64 NOT NULL OPTIONS(description="Memory in GiB"),
  hourly_price FLOAT64 NOT NULL OPTIONS(description="Public on-demand hourly price in currency"),
  currency STRING NOT NULL OPTIONS(description="Currency code, e.g. USD"),
  updated_at TIMESTAMP NOT NULL OPTIONS(description="UTC timestamp of pricing reference update")
)
CLUSTER BY region, machine_type
OPTIONS (
  description = "GCP Compute Engine public on-demand list prices for instance pools"
);
