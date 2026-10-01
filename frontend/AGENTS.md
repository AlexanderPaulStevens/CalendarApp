# AGENTS.md

Guidance for AI agents in the React frontend.

**First rule:** read the actual tree. Only use folders, files, and libraries that exist — or add them when the task clearly needs them.

## Commands

Use the scripts in `package.json` (typically `npm`):

```bash
npm install      # install deps
npm run dev      # Vite dev server (port 5173)
npm run build    # production build
npm run preview  # serve production build locally
npm run lint     # linter (oxlint)
```

Read `README`, `docs/`, and `package.json` for project-specific setup.

## Stack

- **Node.js 20+**
- **React** + **TypeScript**
- **Vite** — dev server and build
- **Tailwind CSS** — via `@tailwindcss/vite`

Add libraries (React Router, TanStack Query, Zod, etc.) only when the feature needs them — verify on the npm registry first.

## Bootstrap

Only if `frontend/` does not exist yet — scaffold from the repo root:

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install -D tailwindcss @tailwindcss/vite oxlint
```

`vite.config.ts` — React, Tailwind v4, port 5173, proxy `/api` to FastAPI on 8000:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

`src/index.css` — Tailwind v4 entry (not v3 `@tailwind` directives):

```css
@import "tailwindcss";
```

`src/main.tsx` — load CSS before the app:

```tsx
import './index.css'
```

Then `npm run dev` → `http://localhost:5173`. Fetch `/api/...` in dev goes through the proxy (no extra CORS setup).

Optional: add a `@/` path alias in `vite.config.ts` and `tsconfig.app.json` when imports get deep.

## Layout

Start from the actual tree. A minimal frontend often looks like:

```text
frontend/
├── package.json
├── vite.config.ts
├── index.html
└── src/
    ├── main.tsx
    ├── index.css         # @import "tailwindcss"
    └── …                 # components, lib/, features/, etc.
```

As the app grows, prefer **feature folders** (`features/<name>/`) over a flat pile of page components. Add `components/ui/`, `hooks/`, and `lib/` when shared code appears — not upfront.

## Conventions

- Functional components; one per file.
- No `any` — use `unknown` and narrow.
- Handle loading, error, and empty states for anything that fetches data.
- Keep fetch logic out of presentational components — a small `lib/api.ts` is enough to start.
- Tailwind utilities in JSX; skip heavy `@apply`.
- Only `VITE_*` env vars in client code — never secrets.

## Priority

Ship the UI wired to the backend before polishing layout or structure.

Done when `npm run build` passes and the happy path works end-to-end.

## Don't

- Invent folder layouts or dependencies that are not in the tree.
- Add routers, query libraries, validators, or global state without a clear need.
- Use `any` or `@ts-ignore` to silence errors.


### Imports

Sort: React → third-party → path alias (`@/`) → relative.

## Configuration

- Commit `.env.example`; never commit real `.env` files.
- Only `VITE_*` vars are exposed to the browser — no secrets, API keys, or private URLs there.
- Use `import.meta.env.VITE_*` in app code, not `process.env`.

## Security

- Treat all external input as untrusted; validate before use.
- Do not store tokens in `localStorage` unless the auth design requires it.
- Do not log credentials or PII to the console.
- Avoid `dangerouslySetInnerHTML` unless content is sanitized.

## Priority: ship end-to-end

Get the UI calling the backend API before polishing layout or abstractions.

Before marking done:

- `npm run build` passes.
- Loading, empty, and error states handled for data-driven UI.
- No secrets in source or committed env files.

## Don't

- Prescribe folders or libraries that are not in the tree yet.
- Put secrets in `VITE_*` variables or client-side code.
- Use `any` or `@ts-ignore` to silence type errors without cause.
- Add global state libraries or new abstractions without explicit need.
- Reference files or modules that do not exist — verify in the tree first.

# Optional (only if the app outgrows a single screen)

| Need | Consider |
|------|----------|
| Multiple pages | React Router |
| Repeated fetch/cache logic | TanStack Query |
| Untrusted API shapes | Zod (or manual guards) at the boundary |
| Shared UI primitives | `components/ui/` |
| Domain-specific code | `features/<name>/` |