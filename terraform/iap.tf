# ==============================================================================
# Cloud Identity-Aware Proxy (IAP) Access Policy
# ==============================================================================

resource "google_iap_web_backend_service_iam_member" "access" {
  for_each = var.enable_load_balancer && var.enable_iap ? toset(var.iap_allowed_members) : toset([])

  provider            = google
  project             = var.project_id
  web_backend_service = google_compute_backend_service.app_backend[0].name
  role                = "roles/iap.httpsResourceAccessor"
  member              = each.value
}
