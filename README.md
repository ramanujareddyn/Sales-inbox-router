# Sales Inbox → Task Router

**candidate_id:** `priya.sharma@gmail.com` (hackathon demo identity; keep this byte-identical in every request and deployment variable)

**Deployed backend URL:** `https://sales-inbox-router-backend.onrender.com` (set to your actual Render URL after deployment)
**Deployed frontend URL:** `https://sales-inbox-router.vercel.app` (set to your actual Vercel URL after deployment)
**Chat endpoint:** same as backend — `POST {backend}/api/chat`

---

## What this is

An automated router for a B2B `sales@` inbox: emails go in, correctly-assigned tasks come out,
junk gets filtered out (not just relocated to a triage pile), and an ops exec gets a screen to
watch it happen and ask it questions instead of trusting a black box.

- **Backend** (`/backend`): FastAPI. Hosts the Task API spec (`/tasks`, `/users`) *and* the
  ingestion + chat layer (`/ingest`, `/api/tasks`, `/api/stats`, `/api/chat`) under one URL.
  Persists to Postgres or SQLite via `DATABASE_URL` — never an in-memory store.
- **Frontend** (`/frontend`): React + Vite. Paste/generate an email batch → see it as a raw
  table → route it → see the resulting tasks → ask questions about what happened, grounded in
  data the backend actually computed (not re-guessed by the LLM at answer time).

## Setup (≤3 commands per side)

### Backend
```bash
cd backend
cp .env.example .env   # fill in GEMINI_API_KEY at minimum
pip install -r requirements.txt --break-system-packages   # or use a venv
uvicorn app.main:app --reload
```
Runs on `http://localhost:8000`. `GET /health` should return `{"status": "ok"}`.

### Frontend
```bash
cd frontend
cp .env.example .env   # set VITE_BACKEND_URL and VITE_CANDIDATE_ID
npm install && npm run dev
```
Runs on `http://localhost:5173`.

## Deployment

- **Backend → Render** (or Railway/Fly): point it at `backend/`, build `pip install -r
  requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Set
  `GEMINI_API_KEY`, `DATABASE_URL` (**use managed Postgres — e.g. Supabase's free tier** — not
  the SQLite default, since free-tier disks are wiped on cold restart and Run 3 of grading
  depends on Run 1's tasks still existing), and `CORS_ORIGINS` to your frontend's deployed
  origin. `render.yaml` in the repo root is a ready-made blueprint.
- **Frontend → Vercel** (or Netlify/Cloudflare Pages): point it at `frontend/`, build `npm run
  build`, output `dist/`. Set `VITE_BACKEND_URL` to your deployed backend URL and
  `VITE_CANDIDATE_ID` to your candidate_id.

Both must be reachable over HTTPS with no auth wall — the grader calls them directly.

## Architecture in one paragraph

`/ingest` is the only entry point the grader posts emails to. For each email it checks an
`EmailLog` table for `(candidate_id, email_id)` — if already seen, it's a no-op (idempotency,
Run 2). Otherwise it classifies the email with Gemini (JSON-mode, retried with backoff, with a
conservative rule-based fallback if Gemini is unreachable), applies two **deterministic**
overrides on top of the LLM's judgment (the 72-hour deadline math and the PSU/government
override — arithmetic and hard rules shouldn't be left to model discretion), then either skips
(spam/newsletter/OOO — logged but no task), patches an existing task if one already exists for
that `thread_id` + `candidate_id` (thread reconciliation, Run 3), or creates a new one. Every
outcome — including skips — is logged, so the chat interface can answer questions about the
whole batch by querying that log and the `tasks` table directly, rather than re-asking Gemini
for facts we already computed (see DECISIONS.md for why this matters for hallucination).

## Repo layout

```
backend/
  app/
    main.py          FastAPI app + CORS
    config.py         env, enums, team roster
    database.py        SQLAlchemy engine/session
    models.py          Task, EmailLog ORM models
    schemas.py         Pydantic validation, exact 400 error shape
    gemini_client.py   Gemini REST calls, retries/backoff
    routing.py         classification prompt + deterministic overrides + fallback
    query_engine.py    chat: NL question -> structured query -> grounded numbers
    routers/
      tasks.py          POST/GET/PATCH/DELETE /tasks, GET /users   (§5 spec)
      ingest.py          POST /ingest                                (§7.1)
      api.py              /api/tasks, /api/stats, /api/chat, sample data
frontend/
  src/
    App.jsx, components/{EmailInput,EmailTable,TaskResults,ChatPanel}.jsx
data/
  team_roster.json
EVALS.md
DECISIONS.md
render.yaml
```

## Before you submit

1. Confirm the demo candidate ID and replace the two example deployment hostnames with the
   actual public URLs assigned by Render and Vercel; they must be byte-identical in the
   submission form.
2. Confirm `GET {backend}/health` and `GET {backend}/users` respond on the public URL, cold.
3. Run the worked examples in the challenge doc (§6) against your deployed `/ingest` and spot
   check `GET /tasks?candidate_id=...` before submitting.
