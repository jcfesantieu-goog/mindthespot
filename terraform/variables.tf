variable "project_id" {
  description = "The Google Cloud Project ID where MindTheSpot resources are deployed."
  type        = string
}

variable "region" {
  description = "The primary Google Cloud region for compute, storage, and serverless resources."
  type        = string
  default     = "europe-west4"
}

variable "environment" {
  description = "Deployment environment identifier (e.g., prod, staging, dev)."
  type        = string
  default     = "prod"
}

variable "artifact_registry_name" {
  description = "The name of the Artifact Registry repository for container images."
  type        = string
  default     = "mindthespot"
}

variable "container_image_tag" {
  description = "The container image tag deployed to Cloud Run."
  type        = string
  default     = "latest"
}

variable "bigquery_dataset_raw" {
  description = "BigQuery dataset ID for raw partitioned preemption and price tables."
  type        = string
  default     = "mindthespot_raw"
}

variable "bigquery_dataset_analytics" {
  description = "BigQuery dataset ID for analytical regime shift and pivot views."
  type        = string
  default     = "mindthespot_analytics"
}

variable "crawler_cron_schedule" {
  description = "Cron schedule expression for the weekly Crawler job execution."
  type        = string
  default     = "0 1 * * 1" # Monday 01:00 UTC
}

variable "crawler_time_zone" {
  description = "Time zone for Cloud Scheduler cron execution."
  type        = string
  default     = "Etc/UTC"
}

variable "crawler_cpu" {
  description = "CPU allocation for the crawler Cloud Run Job."
  type        = string
  default     = "1000m"
}

variable "crawler_memory" {
  description = "Memory allocation for the crawler Cloud Run Job."
  type        = string
  default     = "2Gi"
}

variable "crawler_timeout_seconds" {
  description = "Maximum execution timeout in seconds for the crawler Cloud Run Job."
  type        = number
  default     = 1800
}

variable "app_min_instances" {
  description = "Minimum number of Cloud Run service instances (0 for scale-to-zero)."
  type        = number
  default     = 0
}

variable "app_max_instances" {
  description = "Maximum number of Cloud Run service instances."
  type        = number
  default     = 10
}

variable "app_cpu" {
  description = "CPU allocation for the Cloud Run web application service."
  type        = string
  default     = "1000m"
}

variable "app_memory" {
  description = "Memory allocation for the Cloud Run web application service."
  type        = string
  default     = "1Gi"
}

variable "github_repository" {
  description = "The GitHub repository in format 'owner/repo' for Workload Identity Federation."
  type        = string
  default     = "jcfesantieu-goog/mindthespot"
}

variable "enable_public_access" {
  description = "Allow unauthenticated public access (allUsers) to Cloud Run application service. Disable in orgs enforcing domain restricted sharing."
  type        = bool
  default     = false
}

variable "enable_load_balancer" {
  description = "Deploy a Global External HTTPS Load Balancer with Serverless NEG in front of Cloud Run."
  type        = bool
  default     = true
}

variable "domain_name" {
  description = "Custom domain name for the Load Balancer SSL certificate. Leave empty to auto-generate a wildcard dynamic domain via sslip.io."
  type        = string
  default     = ""
}

variable "enable_iap" {
  description = "Enable Google Cloud Identity-Aware Proxy (IAP) authentication on the Load Balancer backend service."
  type        = bool
  default     = false
}

variable "iap_client_id" {
  description = "OAuth 2.0 Client ID for Identity-Aware Proxy."
  type        = string
  default     = ""
  sensitive   = true
}

variable "iap_client_secret" {
  description = "OAuth 2.0 Client Secret for Identity-Aware Proxy."
  type        = string
  default     = ""
  sensitive   = true
}

variable "iap_allowed_members" {
  description = "List of IAM identities (domains, groups, users) granted roles/iap.httpsResourceAccessor."
  type        = list(string)
  default     = ["domain:jcfesantieu.altostrat.com", "user:sre@jcfesantieu.altostrat.com"]
}
