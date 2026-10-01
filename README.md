# Planning calendar

Spreadsheet-like calendar with a deterministic rule engine for exercise, meals, fridge stock, and shopping. Meal library entries can be drafted from a short chat via OpenAI structured output.

Default timezone: **Europe/Brussels**.

## Run locally

```bash
# terminal 1 — API
cd backend
cp .env.example .env   # set OPENAI_API_KEY for meal chat
uv sync
uv run python -m uvicorn app.main:app --reload --port 8000

# terminal 2 — frontend
cd frontend
npm install
npm run dev
```

- API: http://localhost:8000
- UI: http://localhost:5173 (proxies `/api` to the backend)

Secrets belong in `backend/.env` (gitignored). State is stored in `backend/data/state.json` (seeded on first run). Delete that file to reset.

## Deploy to GCP (Cloud Run + Terraform)

Project: `calendarapp-510309` · Region: `europe-west1` (Belgium).

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

### 3. Build and push the app image

From the **repo root**:

```bash
IMAGE=europe-west1-docker.pkg.dev/calendarapp-510309/calendar/app:latest
docker build -t "$IMAGE" .
docker push "$IMAGE"
```

### 4. Point Cloud Run at your image

```bash
cd infra
terraform apply -var="image=europe-west1-docker.pkg.dev/calendarapp-510309/calendar/app:latest"
```

Or without Terraform:

```bash
gcloud run services update calendar \
  --region=europe-west1 \
  --image=europe-west1-docker.pkg.dev/calendarapp-510309/calendar/app:latest
```

Service URL: `terraform output -raw service_url`

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
