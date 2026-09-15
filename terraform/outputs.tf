output "cloud_run_service_url" {
  description = "Public URL of the deployed MindTheSpot web dashboard and API"
  value       = google_cloud_run_v2_service.app.uri
}

output "artifact_registry_repository" {
  description = "Docker image repository URI in Artifact Registry"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker_repo.name}"
}

output "crawler_job_name" {
  description = "Name of the Cloud Run Job executing spot capacity crawls"
  value       = google_cloud_run_v2_job.crawler.name
}

output "bigquery_raw_dataset" {
  description = "BigQuery dataset storing partitioned raw telemetry"
  value       = google_bigquery_dataset.raw.dataset_id
}

output "bigquery_analytics_dataset" {
  description = "BigQuery dataset storing regime shift and pivot analytical views"
  value       = google_bigquery_dataset.analytics.dataset_id
}

output "workload_identity_provider" {
  description = "Full resource name of the Workload Identity Provider for GitHub Actions"
  value       = google_iam_workload_identity_pool_provider.github_provider.name
}

output "cicd_service_account_email" {
  description = "Email of the CI/CD Service Account used by GitHub Actions"
  value       = google_service_account.cicd.email
}

output "crawler_service_account_email" {
  description = "Email of the dedicated crawler Service Account"
  value       = google_service_account.crawler.email
}

output "app_service_account_email" {
  description = "Email of the dedicated application Service Account"
  value       = google_service_account.app.email
}
