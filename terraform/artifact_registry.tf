resource "google_artifact_registry_repository" "docker_repo" {
  provider = google

  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_registry_name
  description   = "Docker repository for MindTheSpot container images"
  format        = "DOCKER"

  depends_on = [google_project_service.apis]
}
