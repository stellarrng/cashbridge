# CashBridge web client (React + TypeScript)

The landing page, the SME workspace and the Bank review portal. It renders what the FastAPI backend computed and
never calculates money itself.

```bash
cd frontend
npm install        # once (Node 20.19+ or 22.12+, required by Vite 7)
npm run dev        # ONE command: starts the API (:8100) and the UI with hot reload on http://localhost:5173
```

`npm run dev` starts the Python API for you (from the repo's `.venv`) and stops it when you stop the dev server.
If an API is already listening on the dev port it is reused. Change the port with `CASHBRIDGE_API_PORT`.
From the repo root, `make dev` does the same.

Shipping: `npm run build` (or `make web-build`) type-checks and writes `frontend/dist`: two pages (`index.html`,
`app.html`) plus hashed assets. **`frontend/dist` is committed**, so `make run`, Docker, Render and Vercel serve the UI
with no Node step. Rebuild and commit it after every UI change. FastAPI serves it by default
(`CASHBRIDGE_UI_DIR` points it at another build). If the API lives on another origin, build with
`VITE_API_BASE=https://api.example.com` and add the UI's origin to `CASHBRIDGE_ALLOWED_ORIGINS` on the API.
Screens are addressed by the URL hash (`/app#funding`), so no rewrite rules are needed.

## Architecture

Layers, from the bottom. **A layer may only import from the layers below it.**

```
src/
  entries/     landing.tsx, workspace.tsx     composition roots: providers + mount (one per HTML page)
  features/    one folder per business domain / screen  (auth, landing, workspace shell, overview, autopilot,
               decision-center, cash-forecast, receivables, funding, financial-health, bid-simulator,
               contracts, green-finance, audit-trust, settings, assistant, bank/inbox, bank/case)
  entities/    domain types + small shared views     (case snapshot, forecast, funding, autopilot, status)
  shared/      domain-free building blocks           (api client, i18n, preferences, charts, ui, hooks, lib, styles)
```

Rules:

* **Features never import each other.** They share only `entities/` and `shared/`. The one exception is `auth`
  (current user, role strip), which every workspace feature may use. `features/workspace` is the composition
  point: it maps URL hashes to screens (`screens.tsx`, each one a lazy chunk, so a role only downloads the
  screens it opens).
* **Each feature owns its slice:** `api.ts` (endpoints, typed), `types.ts`, its screen, and a `components/`
  folder for pieces used only there. Its `index.ts` is the public surface (screens export `default`).
* **`entities/case`** holds the one read model the SME screens share (`GET /api/snapshot`), refreshed whenever a
  screen opens (`useCase()`), so the sidebar badges, top bar and screens never disagree.
* **No money maths in the browser.** `shared/lib/format.ts` only formats numbers the backend sent.
* **Permissions are a convenience here.** Navigation and buttons follow the server-issued permission list, but the
  server checks every request again.
* Session lives in `sessionStorage` (never `localStorage`); display preferences (language, theme, view, text size,
  motion, contrast) live in `localStorage` and change nothing on the server.
* Interface text is in `shared/i18n/locales/{en,vi,zh}.json`. Engine output (findings, letters, evidence claims)
  stays English on purpose: it is part of the hashed record.
* Styles are the original design system, unchanged (`shared/styles/*.css`): graphite and gold, system fonts, no
  external requests, so the strict `Content-Security-Policy: default-src 'self'` still holds.

Adding a screen: create `features/<name>/` with `api.ts`, `<Name>Screen.tsx` and `index.ts`
(`export { default } from "./<Name>Screen"`), then add one line to `features/workspace/screens.tsx` and, if it
belongs in the menu, to `features/workspace/nav.ts`.
