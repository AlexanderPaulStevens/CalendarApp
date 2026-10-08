# Planning calendar

Spreadsheet-like calendar with a deterministic rule engine for exercise, meals, fridge stock, and shopping. Meal library entries can be drafted from a short chat via OpenAI structured output.

Default timezone: **Europe/Brussels**.

## Run locally

Start both the API and frontend from the **repo root** (Git Bash / WSL / macOS / Linux). Use `./` — do not `cd` into the script:

```bash
./dev.sh up
```

Stop them:

```bash
./dev.sh down
```

(`./backend/scripts/dev.sh` works the same.) The script starts the API on `:8000`, waits for health, installs frontend deps if needed, then runs Vite on `:5173`. Ctrl+C (or `down`) stops both.

- **UI:** http://127.0.0.1:5173 (open this in the browser; proxies `/api` to the backend)
- API: http://127.0.0.1:8000 — `GET /` redirects to the UI; docs at `/docs`

Secrets belong in `backend/.env` (gitignored). State is stored in `backend/data/state.json` (seeded on first run). Delete that file to reset.

## Deploy to GCP (Cloud Run + Terraform)

Project: `calendarapp-510309` · Region: `europe-west1` (Belgium).

App URL: https://calendar-hafalcp6ka-ew.a.run.app

One public Cloud Run service serves the API and the built SPA (same origin). App state is a JSON file on a GCS bucket mounted at `/data`.

**Security:** the service is open to anyone with the URL (no login). Treat the link as sensitive.

### Prerequisites

- [Terraform](https://www.terraform.io/) ≥ 1.5
- [Google Cloud SDK](https://cloud.google.com/sdk) (`gcloud`)
- Docker

```bash
gcloud auth login
gcloud config set project calendarapp-510309
gcloud auth application-default login
gcloud auth configure-docker europe-west1-docker.pkg.dev
```

### 1. Apply infrastructure (Artifact Registry, bucket, secrets, Cloud Run)

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # optional edits
terraform init
terraform apply
```

First apply uses the public Cloud Run hello image as a placeholder so the service exists before your image is pushed.

### 2. Set the OpenAI secret (optional, for meal chat)

```bash
# bash / Git Bash
printf '%s' 'sk-your-key' | gcloud secrets versions add openai-api-key --data-file=-

# PowerShell
"sk-your-key" | gcloud secrets versions add openai-api-key --data-file=-
```

Until you do this, the secret value is the placeholder `not-set` and meal chat will not work.

### 3. Build, push, and deploy

From the **repo root**. Pass the image **digest** to Terraform (not only `:latest`) so Cloud Run gets a new revision after each push.

```bash
# bash / Git Bash
IMAGE="$(terraform -chdir=infra output -raw artifact_registry_image)"
docker build -t "$IMAGE:latest" .
docker push "$IMAGE:latest"
DIGEST="$(gcloud artifacts docker images describe "$IMAGE:latest" --format='get(image_summary.digest)')"
terraform -chdir=infra apply -var="image_digest=$DIGEST"
```

```powershell
# PowerShell
$IMAGE = terraform -chdir=infra output -raw artifact_registry_image
docker build -t "${IMAGE}:latest" .
docker push "${IMAGE}:latest"
$DIGEST = gcloud artifacts docker images describe "${IMAGE}:latest" --format='get(image_summary.digest)'
terraform -chdir=infra apply -var="image_digest=$DIGEST"
```

Or without Terraform:

```bash
gcloud run services update calendar \
  --region=europe-west1 \
  --image="$(terraform -chdir=infra output -raw artifact_registry_image):latest"
```

Service URL: `terraform -chdir=infra output -raw service_url`

### Useful outputs

| Output | Meaning |
| --- | --- |
| `service_url` | Public app URL |
| `artifact_registry_image` | Image path prefix |
| `state_bucket` | GCS bucket for `state.json` |
| `openai_secret_id` | Secret Manager id |

## What works (MVP)

- Day / week / month views; **+** quick-add with replace / keep both / cancel on overlap
- Drag, create, edit, duplicate, delete; origins and conflict flags
- Weekly exercise summary and feasibility; Auto blocks reflow on every change
- **Meals library** with edit, remove, manual add, and chat-to-add (OpenAI structured output → draft → save)
- Meal events, fridge stock, shopping list, store-trip Auto events
- Closed Scheduling Rules catalog (exercise, meals, work, shopping) with parameters
