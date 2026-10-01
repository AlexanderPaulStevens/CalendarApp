output "service_url" {
  description = "Public Cloud Run URL"
  value       = google_cloud_run_v2_service.calendar.uri
}

output "artifact_registry_image" {
  description = "Image path prefix for docker build/push (append :tag)"
  value       = local.image_path
}

output "state_bucket" {
  description = "GCS bucket mounted at /data for state.json"
  value       = google_storage_bucket.state.name
}

output "openai_secret_id" {
  description = "Secret Manager id for OPENAI_API_KEY (add a version before first real deploy)"
  value       = google_secret_manager_secret.openai_api_key.secret_id
}

output "runtime_service_account" {
  description = "Cloud Run runtime service account email"
  value       = google_service_account.runtime.email
}
