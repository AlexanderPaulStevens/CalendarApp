locals {
  apis = [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
  ]

  state_bucket_name = "${var.project_id}-calendar-state"
  ar_repo_id        = "calendar"
  image_path        = "${var.region}-docker.pkg.dev/${var.project_id}/${local.ar_repo_id}/app"
  # Prefer digest so a new docker push is visible to Terraform (tag :latest alone is not).
  resolved_image    = var.image_digest != "" ? "${local.image_path}@${var.image_digest}" : var.image
}

resource "google_project_service" "apis" {
  for_each = toset(local.apis)

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "calendar" {
  location      = var.region
  repository_id = local.ar_repo_id
  description   = "Calendar app container images"
  format        = "DOCKER"

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket" "state" {
  name                        = local.state_bucket_name
  location                    = upper(var.region)
  uniform_bucket_level_access = true
  force_destroy               = false

  depends_on = [google_project_service.apis]
}

resource "google_service_account" "runtime" {
  account_id   = "calendar-runtime"
  display_name = "Calendar Cloud Run runtime"
}

resource "google_storage_bucket_iam_member" "runtime_state" {
  bucket = google_storage_bucket.state.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_secret_manager_secret" "openai_api_key" {
  secret_id = "openai-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_iam_member" "runtime_openai" {
  secret_id = google_secret_manager_secret.openai_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

# Placeholder so Cloud Run can reference version=latest on first apply.
# Replace with a real key: printf '%s' 'sk-...' | gcloud secrets versions add openai-api-key --data-file=-
resource "google_secret_manager_secret_version" "openai_placeholder" {
  secret      = google_secret_manager_secret.openai_api_key.id
  secret_data = "not-set"

  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_cloud_run_v2_service" "calendar" {
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.runtime.email

    # Single instance: JSON file store is not safe for concurrent writers.
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    volumes {
      name = "state"
      gcs {
        bucket    = google_storage_bucket.state.name
        read_only = false
      }
    }

    containers {
      image = local.resolved_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "DATA_PATH"
        value = "/data/state.json"
      }

      env {
        name  = "STATIC_DIR"
        value = "/app/static"
      }

      env {
        name  = "DEFAULT_TIMEZONE"
        value = "Europe/Brussels"
      }

      env {
        name = "OPENAI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.openai_api_key.secret_id
            version = "latest"
          }
        }
      }

      volume_mounts {
        name       = "state"
        mount_path = "/data"
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_storage_bucket_iam_member.runtime_state,
    google_secret_manager_secret_iam_member.runtime_openai,
    google_secret_manager_secret_version.openai_placeholder,
  ]

  lifecycle {
    ignore_changes = [
      # Allow gcloud/docker deploys to bump the image without Terraform fights.
      client,
      client_version,
    ]
  }
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = google_cloud_run_v2_service.calendar.project
  location = google_cloud_run_v2_service.calendar.location
  name     = google_cloud_run_v2_service.calendar.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
