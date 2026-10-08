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
  description = "Full container image for Cloud Run. Used when image_digest is unset. Hello placeholder until the first real image is pushed."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "image_digest" {
  description = "Digest (sha256:...) of the Artifact Registry app image. When set, overrides var.image and forces a Cloud Run revision."
  type        = string
  default     = ""

  validation {
    condition     = var.image_digest == "" || startswith(var.image_digest, "sha256:")
    error_message = "image_digest must be empty or start with sha256:."
  }
}

variable "service_name" {
  description = "Cloud Run service name"
  type        = string
  default     = "calendar"
}
