# Planning calendar

Spreadsheet-like calendar with a deterministic rule engine for exercise, meals, fridge stock, and shopping. Meal library entries can be drafted from a short chat via OpenAI structured output.

## Run locally

```bash
# terminal 1 — API
cd backend
cp .env.example .env   # set OPENAI_API_KEY for meal chat
uv sync
uv run uvicorn app.main:app --reload --port 8000

# terminal 2 — frontend
cd frontend
npm install
npm run dev
```

- API: http://localhost:8000
- UI: http://localhost:5173 (proxies `/api` to the backend)

Secrets belong in `backend/.env` (gitignored). State is stored in `backend/data/state.json` (seeded on first run). Delete that file to reset.

### Note (Google Drive / non-NTFS)

If `npm install` fails with tar write errors, install deps on a local NTFS path and run Vite from there:

```powershell
$local = "$env:LOCALAPPDATA\calendar-frontend-deps"
New-Item -ItemType Directory -Force -Path $local | Out-Null
Copy-Item frontend\package.json,frontend\vite.config.ts,frontend\index.html,frontend\tsconfig*.json $local -Force
Copy-Item frontend\src $local\src -Recurse -Force
cd $local
npm install
npm run dev
```

Re-copy `frontend\src` into `$local\src` after editing sources on Drive.

## What works (MVP)

- Day / week / month views; **+** quick-add with replace / keep both / cancel on overlap
- Drag, create, edit, duplicate, delete; origins and conflict flags
- Weekly exercise summary, feasibility, suggestions, rebuild auto blocks
- **Meals library** with edit, remove, manual add, and chat-to-add (OpenAI structured output → draft → save)
- Meal events, fridge stock, shopping list, run-out reminders
- Rules list (enable / disable) and seeded starter rules
