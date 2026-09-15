# ==============================================================================
# Service Account: Crawler (Cloud Run Job)
# ==============================================================================
resource "google_service_account" "crawler" {
  project      = var.project_id
  account_id   = "mindthespot-crawler"
  display_name = "MindTheSpot Crawler Service Account"
  description  = "Runs weekly preemption & price capacity history ingestion"
}

resource "google_project_iam_member" "crawler_compute_viewer" {
  project = var.project_id
  role    = "roles/compute.viewer"
  member  = "serviceAccount:${google_service_account.crawler.email}"
}

resource "google_project_iam_member" "crawler_bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.crawler.email}"
}

# ==============================================================================
# Service Account: Application / Dashboard (Cloud Run Service)
# ==============================================================================
resource "google_service_account" "app" {
  project      = var.project_id
  account_id   = "mindthespot-app"
  display_name = "MindTheSpot Application Service Account"
  description  = "Serves FastAPI backend & reads analytical BigQuery views"
}

resource "google_project_iam_member" "app_bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.app.email}"
}

# ==============================================================================
# Service Account: Cloud Scheduler Invoker
# ==============================================================================
resource "google_service_account" "scheduler" {
  project      = var.project_id
  account_id   = "mindthespot-scheduler"
  display_name = "MindTheSpot Cloud Scheduler Service Account"
  description  = "Invokes Cloud Run Job on a scheduled cron"
}

# ==============================================================================
# Service Account & Workload Identity Federation: GitHub Actions CI/CD GitOps
# ==============================================================================
resource "google_service_account" "cicd" {
  project      = var.project_id
  account_id   = "mindthespot-cicd"
  display_name = "MindTheSpot CI/CD Service Account"
  description  = "Used by GitHub Actions GitOps workflow to build, push and deploy"
}

resource "google_project_iam_member" "cicd_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "cicd_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "cicd_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "cicd_scheduler_admin" {
  project = var.project_id
  role    = "roles/cloudscheduler.admin"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "cicd_bigquery_admin" {
  project = var.project_id
  role    = "roles/bigquery.admin"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "cicd_storage_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "cicd_project_iam_admin" {
  project = var.project_id
  role    = "roles/resourcemanager.projectIamAdmin"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "cicd_wif_admin" {
  project = var.project_id
  role    = "roles/iam.workloadIdentityPoolAdmin"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "cicd_sa_admin" {
  project = var.project_id
  role    = "roles/iam.serviceAccountAdmin"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "cicd_security_admin" {
  project = var.project_id
  role    = "roles/iam.securityAdmin"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "cicd_network_admin" {
  project = var.project_id
  role    = "roles/compute.networkAdmin"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "cicd_lb_admin" {
  project = var.project_id
  role    = "roles/compute.loadBalancerAdmin"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "cicd_iap_admin" {
  project = var.project_id
  role    = "roles/iap.admin"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

# Workload Identity Pool
resource "google_iam_workload_identity_pool" "github_pool" {
  project                   = var.project_id
  workload_identity_pool_id = "mindthespot-github-pool"
  display_name              = "MindTheSpot GitHub Actions Pool"
  description               = "Identity pool for GitHub Actions OIDC federation"
}

# Workload Identity Provider
resource "google_iam_workload_identity_pool_provider" "github_provider" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "mindthespot-gh-provider"
  display_name                       = "MindTheSpot GitHub Provider"
  description                        = "OIDC Provider for GitHub Actions"

  attribute_condition = "assertion.repository == '${var.github_repository}'"

  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.actor"            = "assertion.actor"
    "attribute.repository"       = "assertion.repository"
    "attribute.repository_owner" = "assertion.repository_owner"
  }

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Allow GitHub Actions repository to impersonate cicd service account
resource "google_service_account_iam_member" "cicd_wif_binding" {
  service_account_id = google_service_account.cicd.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository/${var.github_repository}"
}
