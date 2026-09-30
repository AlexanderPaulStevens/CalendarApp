# AGENTS.md

Guidance for AI agents working in the Python backend. Verify what exists in the tree before importing or creating modules.

## Commands

```bash
uv sync                                          # install deps
uv run uvicorn app.main:app --reload --port 8000 # start API (FastAPI)
uv add <pkg>                                     # add a dependency
```

Read `README`, `docs/`, and `pyproject.toml` for project-specific setup.

## Stack

- **Python 3.12+** — `uv` for deps and commands
- **FastAPI** + **Uvicorn** — REST API for the React + Vite + Tailwind frontend
- **Pydantic v2** — settings and request/response models

## Bootstrap

When `backend/app/` does not exist yet, scaffold from the repository root:

```bash
mkdir -p backend/app
cd backend
uv init
uv add fastapi "uvicorn[standard]" pydantic-settings
```

`app/config.py` — load secrets from `backend/.env` (run commands from `backend/`):

```python
import pydantic_settings


class Settings(pydantic_settings.BaseSettings):
    # Add required env vars as typed fields (fail fast if missing)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
```

`app/main.py` — FastAPI app, CORS for Vite, mount routers:

```python
import fastapi
from fastapi.middleware import cors

app = fastapi.FastAPI()

app.add_middleware(
    cors.CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# app.include_router(...)  # add as routes are created
```

Run with `uv run uvicorn app.main:app --reload --port 8000`.

## Layout

Start from the actual tree. A minimal backend often looks like:

```text
backend/
├── pyproject.toml
├── uv.lock
└── app/
    ├── main.py
    └── config.py
```

Add folders only when the app needs them:


| Folder          | Purpose                                                      |
| --------------- | ------------------------------------------------------------ |
| `router/`       | Thin HTTP handlers (`APIRouter` modules)                     |
| `schemas/`      | Pydantic request/response models                             |
| `services/`     | Business logic and orchestration                             |
| `repositories/` | Data access (only when persistence warrants it)              |
| `tests/`        | Tests; mirror the app structure as it grows                  |


For LLM/agent workflows, a `core/` package (agents, prompts, workflows) is fine when explicitly needed — keep dependencies one-way inward.

## Conventions

### Imports

Follow the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) §2.2, §3.2, and §3.13:

- Import packages and modules only. Do not import classes, functions, or constants. Refer to them as `module.Name`.
- Exceptions that may import symbols: `typing`, `collections.abc`, and `typing_extensions`.
- Use the full package path. No relative imports (`from . import x`) and no re-exports through a package `__init__.py`.
- One import per line. Group `__future__`, then the standard library, then third-party, then this repo. Leave a blank line between groups. Sort each group lexicographically by the full path.
- Keep each line to 80 characters.

### FastAPI

- Create the app in `main.py`; mount routers via `APIRouter` from whichever package holds them.
- Use **Pydantic models** for request bodies, query params, and responses — not raw dicts.
- Inject shared deps (`settings`, services) with `Depends()` — do not instantiate globals in routes.
- Raise `HTTPException` for expected client errors; use handlers for unexpected failures (no raw tracebacks to clients).
- Enable **CORS** for the Vite dev origin (`http://localhost:5173`) when the React app calls the API locally.
- Keep routes to validate → call service → return schema; no business logic inline.

```python
import fastapi

router = fastapi.APIRouter(prefix="/items", tags=["items"])

@router.get("/{item_id}", response_model=ItemOut)
def get_item(
    item_id: int,
    svc: ItemService = fastapi.Depends(get_item_service),
) -> ItemOut:
    item = svc.get(item_id)
    if item is None:
        raise fastapi.HTTPException(
            status_code=404, detail="Item not found"
        )
    return item
```

## Persistence

Use **local, in-process storage** by default — in-memory dicts/lists, JSON or other files under the project.

When SQL is explicitly requested, add `repositories/` and ORM models and route DB access through repositories only.

## Configuration

- Secrets live in `backend/.env`. Fail fast when required config is missing. Run `uvicorn` from `backend/` so the relative `env_file` resolves correctly.
- Use `config.py` with `pydantic_settings.BaseSettings`. Import the `config` module and read `config.settings`. Never call `os.getenv` or `load_dotenv` in app modules.
- Never hardcode secrets, API keys, or credentials.

## Security (always apply)

- Validate all external input via schema validation at boundaries.
- Sanitize error responses; do not expose stack traces, internal paths, or DB details to clients.
- Do not log sensitive data (tokens, credentials, PII).
- Before adding dependencies: confirm the package exists on the official registry and comply with license policy.
- After security-sensitive changes, self-review before finishing (see the `security` skill).

## Priority: ship end-to-end

Get the full flow working first — API and frontend wired together — before polishing internals.

Before marking done:

- Start the API and confirm the React app can call it successfully.
- Exercise the happy path manually; fix blockers before refactors or edge cases.
- Only add tests or lint passes when explicitly requested.

## Don't

- Scatter configuration reads across app code.
- Reference files or modules that do not exist — verify in the tree first.
- Assume a folder layout from this doc — add structure as the app grows.
- Commit secrets or leak sensitive info in logs, errors, or docs.
