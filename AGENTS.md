# Agent Instructions

Read this before touching code. Area-specific guidance:

- `[backend/AGENTS.md](backend/AGENTS.md)` — Python API, `uv`
- `[frontend/AGENTS.md](frontend/AGENTS.md)` — React SPA, Vite, TypeScript, Tailwind CSS

## Repo

 **Verify the tree before coding** — these docs describe the intended stack and conventions, not a fixed folder layout. Do not assume modules, routes, or dependencies that are not present yet.

```text
Calendar/
├── AGENTS.md
├── README.md
├── requirements.md
├── .cursor/
│   ├── agents/           # Cursor subagents (e.g. redteam)
│   └── skills/           # Cursor agent skills
├── docs/                 # briefs, notes, diagrams
├── backend/              # Python project (uv-managed, FastAPI)
│   ├── .env.example      # template for backend .env
│   └── data/             # JSON state (gitignored)
└── frontend/             # React SPA (Vite, TypeScript, Tailwind CSS)
```

## Stack

- **Backend** — Python 3.12+ · `uv` for deps and commands; FastAPI + Uvicorn REST API (see `[backend/AGENTS.md](backend/AGENTS.md)`)
- **Frontend** — React + TypeScript · Vite · Tailwind CSS (see `[frontend/AGENTS.md](frontend/AGENTS.md)`)
- **Planner** — Deterministic `PlanEngine` in the backend (no LLM)

## Persistence

Default to **local, in-process storage** — in-memory structures, JSON/files on disk, or similar. Do **not** add SQL databases, ORMs (e.g. SQLModel), migrations, Docker DB services, or a repository layer unless the user explicitly asks.

## Dependencies

Write it yourself by default. Add a library only when the alternative is non-trivial or reinvents a standard (HTTP clients, LLM SDKs, etc.).

- In `backend/`, use `uv sync`, `uv run`, and `uv add`. Prefer the repo's `uv.lock` and `.venv` workflow.
- In `frontend/`, use **npm** and the scripts in `package.json` (see `[frontend/AGENTS.md](frontend/AGENTS.md)`).

## Running locally

```bash
# terminal 1 — API
cd backend && uv run uvicorn app.main:app --reload --port 8000

# terminal 2 — frontend
cd frontend && npm run dev
```

API on `http://localhost:8000`, frontend on `http://localhost:5173` (proxies `/api` to the backend).

## Cursor agents & skills

### Agents

Custom subagents live in `[.cursor/agents/](.cursor/agents/)`.


| Agent   | Purpose                                                |
| ------- | ------------------------------------------------------ |
| redteam | Read-only security audit (findings only; no code edits) |

### Skills

Project skills live in `[.cursor/skills/](.cursor/skills/)`. Cursor discovers them automatically; name a skill or match its description to apply it.


| Skill                  | Purpose                                               |
| ---------------------- | ----------------------------------------------------- |
| security               | Security invariants, self-review, supply-chain checks |
| google-python-style    | Google Python Style Guide pass (imports, types)       |
| markdown-to-excalidraw | Bullet/flow markdown → `.excalidraw` diagram          |
| create-skill           | Scaffold a new Cursor skill                           |
| grilling               | Stress-test a plan or design (no doc updates)         |
| grill-with-docs        | Grill a plan; update CONTEXT.md and ADRs inline       |
| domain-modeling        | Domain glossary and ADR discipline                    |


For security-sensitive work, apply the `security` skill before marking a task done. Use the `redteam` agent for a dedicated read-only audit.

## Configuration

- Optional env vars go in `backend/.env` (see `backend/.env.example`). `OPENAI_API_KEY` is required only for meal-library chat. Run backend commands from `backend/`.
- Backend: centralize settings in `config.py` with `pydantic_settings.BaseSettings`. Do not scatter `os.getenv` or `load_dotenv` across app code.
- Frontend: only `VITE_*` vars are exposed to the browser — no secrets in client env (see `[frontend/AGENTS.md](frontend/AGENTS.md)`).
- Fail fast when required config is missing.

## Code style

- Small, obvious functions. Extract on the third caller, not for a hypothetical reuse.
- Validate at boundaries only: HTTP input, external APIs, untrusted parsing.
- No premature abstraction, speculative feature flags, or backwards-compat shims unless asked.
- Comments explain *why*, not *what*.

## Priority: ship end-to-end

Get the full flow working first — API, plan engine, and frontend wired together — before polishing internals. See `[backend/AGENTS.md](backend/AGENTS.md)` and `[frontend/AGENTS.md](frontend/AGENTS.md)` for area-specific checklists.