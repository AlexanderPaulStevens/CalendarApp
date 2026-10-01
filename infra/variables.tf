variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "calendarapp-510309"
}

variable "region" {
  description = "GCP region (Belgium)"
  type        = string
  default     = "europe-west1"
}

variable "image" {
  description = "Container image for Cloud Run (Artifact Registry). Use the hello placeholder until the first image is pushed."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "service_name" {
  description = "Cloud Run service name"
  type        = string
  default     = "calendar"
}
