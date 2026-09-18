# ==============================================================================
# Cloud Run Service: MindTheSpot Application (FastAPI + React UI)
# ==============================================================================
resource "google_cloud_run_v2_service" "app" {
  provider = google

  project  = var.project_id
  name     = "mindthespot-app"
  location = var.region
  ingress  = var.enable_load_balancer ? "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER" : "INGRESS_TRAFFIC_ALL"
  custom_audiences = compact(var.enable_load_balancer ? [
    local.effective_domain != "" ? "https://${local.effective_domain}" : "",
    var.iap_client_id
  ] : [])

  template {
    service_account = google_service_account.app.email

    scaling {
      min_instance_count = var.app_min_instances
      max_instance_count = var.app_max_instances
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_registry_name}/mindthespot:${var.container_image_tag}"

      resources {
        limits = {
          cpu    = var.app_cpu
          memory = var.app_memory
        }
      }

      ports {
        container_port = 8080
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "BIGQUERY_DATASET_RAW"
        value = google_bigquery_dataset.raw.dataset_id
      }

      env {
        name  = "BIGQUERY_DATASET_ANALYTICS"
        value = google_bigquery_dataset.analytics.dataset_id
      }

      env {
        name  = "SYNC_PREWARM"
        value = "true"
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_bigquery_dataset.raw,
    google_bigquery_dataset.analytics,
  ]
}

# Public Ingress Policy (if enabled)
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  count = var.enable_public_access ? 1 : 0

  project  = var.project_id
  location = google_cloud_run_v2_service.app.location
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ==============================================================================
# Cloud Run Job: MindTheSpot Ingestion Crawler
# ==============================================================================
resource "google_cloud_run_v2_job" "crawler" {
  provider = google

  project  = var.project_id
  name     = "mindthespot-crawler"
  location = var.region

  template {
    template {
      service_account = google_service_account.crawler.email
      timeout         = "${var.crawler_timeout_seconds}s"
      max_retries     = 1

      containers {
        image   = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_registry_name}/mindthespot:${var.container_image_tag}"
        command = ["mindthespot", "crawl", "--output", "bigquery"]

        resources {
          limits = {
            cpu    = var.crawler_cpu
            memory = var.crawler_memory
          }
        }

        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "BIGQUERY_DATASET_RAW"
          value = google_bigquery_dataset.raw.dataset_id
        }
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_bigquery_dataset.raw,
  ]
}

# Allow Scheduler Service Account to execute Crawler Job
resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  project  = var.project_id
  location = google_cloud_run_v2_job.crawler.location
  name     = google_cloud_run_v2_job.crawler.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}
