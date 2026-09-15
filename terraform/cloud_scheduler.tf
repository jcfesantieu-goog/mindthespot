# ==============================================================================
# Cloud Scheduler: Weekly Ingestion Trigger
# ==============================================================================
resource "google_cloud_scheduler_job" "crawler_trigger" {
  provider = google

  project          = var.project_id
  region           = var.region
  name             = "mindthespot-crawler-weekly"
  description      = "Triggers weekly execution of the MindTheSpot crawler Cloud Run Job"
  schedule         = var.crawler_cron_schedule
  time_zone        = var.crawler_time_zone
  attempt_deadline = "320s"

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.crawler.name}:run"

    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }

  depends_on = [
    google_project_service.apis,
    google_cloud_run_v2_job_iam_member.scheduler_invoker,
  ]
}
