# ==============================================================================
# BigQuery Raw Telemetry Dataset & Partitioned Tables
# ==============================================================================
resource "google_bigquery_dataset" "raw" {
  project     = var.project_id
  dataset_id  = var.bigquery_dataset_raw
  location    = var.region
  description = "Raw ingested telemetry snapshots from GCP Capacity History API"

  access {
    role          = "roles/bigquery.dataEditor"
    user_by_email = google_service_account.crawler.email
  }

  access {
    role          = "roles/bigquery.dataViewer"
    user_by_email = google_service_account.app.email
  }

  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }

  depends_on = [google_project_service.apis]
}

resource "google_bigquery_table" "preemption_history" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.raw.dataset_id
  table_id            = "preemption_history"
  description         = "Daily snapshot partitions of 30-day GCP Spot preemption rate history"
  deletion_protection = false

  time_partitioning {
    type  = "DAY"
    field = "snapshot_date"
  }

  clustering = ["region", "zone", "machine_type"]

  schema = jsonencode([
    { name = "snapshot_date", type = "DATE", mode = "REQUIRED", description = "Date of crawl execution snapshot" },
    { name = "crawled_at", type = "TIMESTAMP", mode = "REQUIRED", description = "UTC timestamp of crawl execution" },
    { name = "region", type = "STRING", mode = "REQUIRED", description = "GCP region identifier" },
    { name = "zone", type = "STRING", mode = "REQUIRED", description = "GCP zone identifier" },
    { name = "machine_type", type = "STRING", mode = "REQUIRED", description = "GCP machine type" },
    { name = "family", type = "STRING", mode = "REQUIRED", description = "Machine family prefix" },
    { name = "telemetry_date", type = "DATE", mode = "REQUIRED", description = "Observation date YYYY-MM-DD" },
    { name = "preemption_rate", type = "FLOAT64", mode = "REQUIRED", description = "Preemption rate 0.0 to 1.0" },
    { name = "is_watchlist", type = "BOOL", mode = "NULLABLE", description = "Watchlist inclusion flag" },
    { name = "custom_label", type = "STRING", mode = "NULLABLE", description = "Custom workload label" }
  ])
}

resource "google_bigquery_table" "price_history" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.raw.dataset_id
  table_id            = "price_history"
  description         = "Daily snapshot partitions of 1-year GCP Spot interval pricing history"
  deletion_protection = false

  time_partitioning {
    type  = "DAY"
    field = "snapshot_date"
  }

  clustering = ["region", "machine_type"]

  schema = jsonencode([
    { name = "snapshot_date", type = "DATE", mode = "REQUIRED", description = "Date of crawl execution snapshot" },
    { name = "crawled_at", type = "TIMESTAMP", mode = "REQUIRED", description = "UTC timestamp of crawl execution" },
    { name = "region", type = "STRING", mode = "REQUIRED", description = "GCP region identifier" },
    { name = "machine_type", type = "STRING", mode = "REQUIRED", description = "GCP machine type" },
    { name = "family", type = "STRING", mode = "REQUIRED", description = "Machine family prefix" },
    { name = "interval_start", type = "TIMESTAMP", mode = "REQUIRED", description = "Price interval start timestamp" },
    { name = "interval_end", type = "TIMESTAMP", mode = "NULLABLE", description = "Price interval end timestamp" },
    { name = "hourly_price", type = "FLOAT64", mode = "REQUIRED", description = "Hourly spot price" },
    { name = "currency", type = "STRING", mode = "REQUIRED", description = "Currency code" }
  ])
}

resource "google_bigquery_table" "on_demand_pricing" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.raw.dataset_id
  table_id            = "on_demand_pricing"
  description         = "GCP Compute Engine public on-demand list prices for instance pools"
  deletion_protection = false

  clustering = ["region", "machine_type"]

  schema = jsonencode([
    { name = "region", type = "STRING", mode = "REQUIRED", description = "GCP region identifier" },
    { name = "machine_type", type = "STRING", mode = "REQUIRED", description = "GCP machine type" },
    { name = "family", type = "STRING", mode = "REQUIRED", description = "Machine family prefix" },
    { name = "vcpus", type = "INT64", mode = "REQUIRED", description = "Number of guest vCPUs" },
    { name = "memory_gb", type = "FLOAT64", mode = "REQUIRED", description = "Memory in GiB" },
    { name = "hourly_price", type = "FLOAT64", mode = "REQUIRED", description = "Public on-demand hourly price" },
    { name = "currency", type = "STRING", mode = "REQUIRED", description = "Currency code" },
    { name = "updated_at", type = "TIMESTAMP", mode = "REQUIRED", description = "UTC timestamp of pricing reference update" }
  ])
}

resource "google_bigquery_table" "user_watchlists" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.raw.dataset_id
  table_id            = "user_watchlists"
  description         = "Persistent user-curated workload watchlists and starred pools"
  deletion_protection = false

  clustering = ["user_email", "region"]

  schema = jsonencode([
    { name = "user_email", type = "STRING", mode = "REQUIRED", description = "User identity from Cloud IAP header or local dev context" },
    { name = "watchlist_type", type = "STRING", mode = "REQUIRED", description = "WORKLOAD_TARGET or STARRED_POOL" },
    { name = "target_name", type = "STRING", mode = "NULLABLE", description = "User-friendly workload target name" },
    { name = "region", type = "STRING", mode = "REQUIRED", description = "GCP region identifier" },
    { name = "zone", type = "STRING", mode = "NULLABLE", description = "GCP zone identifier for individual pool" },
    { name = "machine_type", type = "STRING", mode = "NULLABLE", description = "GCP machine type" },
    { name = "zones_json", type = "STRING", mode = "NULLABLE", description = "JSON array of targeted zones" },
    { name = "machine_types_json", type = "STRING", mode = "NULLABLE", description = "JSON array of targeted machine types" },
    { name = "custom_label", type = "STRING", mode = "NULLABLE", description = "Custom workload label or purpose description" },
    { name = "alert_threshold_z", type = "FLOAT64", mode = "NULLABLE", description = "Custom volatility alert threshold Z-score" },
    { name = "alert_threshold_delta", type = "FLOAT64", mode = "NULLABLE", description = "Custom preemption rate delta threshold" },
    { name = "is_active", type = "BOOL", mode = "REQUIRED", description = "Active state flag; false denotes soft-deleted target" },
    { name = "updated_at", type = "TIMESTAMP", mode = "REQUIRED", description = "UTC timestamp of last creation, mutation or toggle" }
  ])
}

# Table-level least-privilege IAM: Cloud Run app can ONLY edit user_watchlists table
resource "google_bigquery_table_iam_member" "app_user_watchlists_editor" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.raw.dataset_id
  table_id   = google_bigquery_table.user_watchlists.table_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.app.email}"
}

# ==============================================================================
# BigQuery Analytical Views Dataset & Views
# ==============================================================================
resource "google_bigquery_dataset" "analytics" {
  project     = var.project_id
  dataset_id  = var.bigquery_dataset_analytics
  location    = var.region
  description = "Analytical views for statistical regime shifts and pivot recommendations"

  access {
    role          = "roles/bigquery.dataViewer"
    user_by_email = google_service_account.app.email
  }

  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }

  depends_on = [google_project_service.apis]
}

# View 1: Regime Shifts View
resource "google_bigquery_table" "v_regime_shifts" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.analytics.dataset_id
  table_id            = "v_regime_shifts"
  description         = "Computes rolling 7d vs 23d baseline Z-score and flags price hikes"
  deletion_protection = false

  view {
    use_legacy_sql = false
    query = templatefile("${path.module}/../sql/views/templates/v_regime_shifts.sql.tpl", {
      project     = var.project_id
      dataset_raw = google_bigquery_dataset.raw.dataset_id
    })
  }

  depends_on = [google_bigquery_table.preemption_history, google_bigquery_table.price_history, google_bigquery_table.on_demand_pricing]
}

# View 2: Pivot Recommendations View
resource "google_bigquery_table" "v_pivot_recommendations" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.analytics.dataset_id
  table_id            = "v_pivot_recommendations"
  description         = "Identifies fallback sibling zone and equivalent family pivot recommendations"
  deletion_protection = false

  view {
    use_legacy_sql = false
    query = templatefile("${path.module}/../sql/views/templates/v_pivot_recommendations.sql.tpl", {
      project           = var.project_id
      dataset_analytics = google_bigquery_dataset.analytics.dataset_id
    })
  }

  depends_on = [google_bigquery_table.v_regime_shifts]
}
