locals {
  required_services = [
    "compute.googleapis.com",
    "run.googleapis.com",
    "cloudscheduler.googleapis.com",
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "cloudresourcemanager.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each = toset(local.required_services)

  project = var.project_id
  service = each.key

  disable_on_destroy = false
}
