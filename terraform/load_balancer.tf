# ==============================================================================
# Global External Application Load Balancer with Serverless NEG & Managed SSL
# ==============================================================================

resource "google_compute_global_address" "app_ip" {
  count = var.enable_load_balancer ? 1 : 0

  provider = google
  project  = var.project_id
  name     = "mindthespot-lb-ip"
}

locals {
  lb_ip = try(google_compute_global_address.app_ip[0].address, "")
  # If domain_name is provided, use it; otherwise compute sslip.io wildcard domain from static IP
  effective_domain = var.domain_name != "" ? var.domain_name : (local.lb_ip != "" ? "spot-${replace(local.lb_ip, ".", "-")}.sslip.io" : "")
}

# Regional Serverless Network Endpoint Group (NEG) targeting Cloud Run
resource "google_compute_region_network_endpoint_group" "serverless_neg" {
  count = var.enable_load_balancer ? 1 : 0

  provider              = google
  project               = var.project_id
  name                  = "mindthespot-serverless-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region

  cloud_run {
    service = google_cloud_run_v2_service.app.name
  }
}

# Backend Service for Cloud Run Serverless NEG
resource "google_compute_backend_service" "app_backend" {
  count = var.enable_load_balancer ? 1 : 0

  provider              = google
  project               = var.project_id
  name                  = "mindthespot-backend-service"
  protocol              = "HTTP"
  port_name             = "http"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  timeout_sec           = 300
  enable_cdn            = false

  backend {
    group = google_compute_region_network_endpoint_group.serverless_neg[0].id
  }

  dynamic "iap" {
    for_each = var.enable_iap && var.iap_client_id != "" ? [1] : []
    content {
      enabled              = true
      oauth2_client_id     = var.iap_client_id
      oauth2_client_secret = var.iap_client_secret
    }
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

# Google-Managed SSL Certificate
resource "google_compute_managed_ssl_certificate" "app_cert" {
  count = var.enable_load_balancer ? 1 : 0

  provider = google
  project  = var.project_id
  name     = "mindthespot-managed-cert"

  managed {
    domains = [local.effective_domain]
  }

  lifecycle {
    create_before_destroy = true
  }
}

# HTTPS URL Map
resource "google_compute_url_map" "default" {
  count = var.enable_load_balancer ? 1 : 0

  provider        = google
  project         = var.project_id
  name            = "mindthespot-url-map"
  default_service = google_compute_backend_service.app_backend[0].id
}

# Target HTTPS Proxy
resource "google_compute_target_https_proxy" "default" {
  count = var.enable_load_balancer ? 1 : 0

  provider         = google
  project          = var.project_id
  name             = "mindthespot-https-proxy"
  url_map          = google_compute_url_map.default[0].id
  ssl_certificates = [google_compute_managed_ssl_certificate.app_cert[0].id]
}

# Global Forwarding Rule for HTTPS (Port 443)
resource "google_compute_global_forwarding_rule" "https" {
  count = var.enable_load_balancer ? 1 : 0

  provider              = google
  project               = var.project_id
  name                  = "mindthespot-https-forwarding-rule"
  target                = google_compute_target_https_proxy.default[0].id
  ip_address            = google_compute_global_address.app_ip[0].address
  port_range            = "443"
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

# HTTP to HTTPS Redirect URL Map
resource "google_compute_url_map" "http_redirect" {
  count = var.enable_load_balancer ? 1 : 0

  provider = google
  project  = var.project_id
  name     = "mindthespot-http-redirect-url-map"

  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

# Target HTTP Proxy for Redirection
resource "google_compute_target_http_proxy" "http_redirect" {
  count = var.enable_load_balancer ? 1 : 0

  provider = google
  project  = var.project_id
  name     = "mindthespot-http-redirect-proxy"
  url_map  = google_compute_url_map.http_redirect[0].id
}

# Global Forwarding Rule for HTTP (Port 80) -> Redirects to HTTPS
resource "google_compute_global_forwarding_rule" "http" {
  count = var.enable_load_balancer ? 1 : 0

  provider              = google
  project               = var.project_id
  name                  = "mindthespot-http-forwarding-rule"
  target                = google_compute_target_http_proxy.http_redirect[0].id
  ip_address            = google_compute_global_address.app_ip[0].address
  port_range            = "80"
  load_balancing_scheme = "EXTERNAL_MANAGED"
}
