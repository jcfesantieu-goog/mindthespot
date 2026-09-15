# ==============================================================================
# Cloud Identity-Aware Proxy (IAP) Access Policy & Service Identity
# ==============================================================================

# User / Domain authorization for IAP
resource "google_iap_web_backend_service_iam_member" "access" {
  for_each = var.enable_load_balancer && var.enable_iap ? toset(var.iap_allowed_members) : toset([])

  provider            = google
  project             = var.project_id
  web_backend_service = google_compute_backend_service.app_backend[0].name
  role                = "roles/iap.httpsResourceAccessor"
  member              = each.value
}

# Service identity for IAP
resource "google_project_service_identity" "iap_sa" {
  provider = google-beta
  project  = var.project_id
  service  = "iap.googleapis.com"
}

# Grant Cloud Run invoker to IAP service account so IAP can forward authenticated requests
resource "google_cloud_run_v2_service_iam_member" "iap_invoker" {
  count = var.enable_load_balancer && var.enable_iap ? 1 : 0

  project  = var.project_id
  location = google_cloud_run_v2_service.app.location
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_project_service_identity.iap_sa.email}"
}

