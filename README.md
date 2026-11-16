# InnerSpace

**A between-sessions notebook for people in therapy or psychiatric care.** Clients log what happens between appointments, and an AI assistant helps them turn their own entries into a short, source-cited summary they review, approve and choose to share with their clinician.

> [!WARNING]
> **Portfolio / demo project.** InnerSpace uses **synthetic data only**. It is not a medical device, does not diagnose, and does not provide treatment or crisis support. Do not enter real personal or health information.
> If you are in crisis, contact your local emergency number (112 in Türkiye).

## Status

🚧 **Active development.** Phases 1 (backend foundation), 2 (authentication & authorization), 3 (AI summaries), 4 (background jobs), 5 (evaluation, rate limiting, observability) and the React frontend are complete; Phase 6 (Docker, CI, Render Blueprint), Phase 7 (appointments, support plan) and Phase 8 (summary topics, in-app reminders, data export and account deletion) are done.

**Live demo:** https://innerspace-web.onrender.com (synthetic data only; demo accounts are created by the seed script, credentials are not published here).

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 | Repository, tooling, secret scanning | ✅ Done |
| 1 | FastAPI app, PostgreSQL, SQLAlchemy models, Alembic, entry CRUD, structured logging | ✅ Done |
| 2 | JWT auth, roles, RBAC, organization-level isolation, authorization tests | ✅ Done |
| 3 | AI summaries: structured output, citations, guardrails, human-in-the-loop sharing | ✅ Done |
| 4 | Background jobs (Redis, Celery), retries, idempotency | ✅ Done |
| 5 | AI evaluation, rate limiting, observability, LLM tracing | ✅ Done |
| 6 | Docker, CI/CD, Render deployment | ✅ Done (Blueprint ready; deploy is a manual step) |
| 7 | Appointments (clinician-managed, read-only for clients) and "Planım" support plan with the "O an" card | ✅ Done |
| 8 | Summary topics, in-app reminders, data export and account deletion | ✅ Done |
| — | React + TypeScript frontend, built alongside the backend | ✅ Done (client, clinician and clinic-admin screens) |

## What it does (planned v1)

| | |
|---|---|
| **Log** | Quick entries, panic episode logs, medication & side-effect notes, avoidance notes |
| **Prepare** | AI-assisted pre-appointment summary — every statement links back to the client's own entries |
| **Review & share** | Nothing leaves the client's account without explicit approval; sharing is revocable |
| **After session** | Short note structured into "what we discussed / what I'll try / questions for next time" |
| **My plan** | Support plan ("Planım") written by the client, with an "O an" card for difficult moments; optionally shared read-only with the clinician |
| **Appointments** | Managed by the assigned clinician, read-only for the client; a summary can be prepared for a specific appointment |
| **Topics to talk about** | The client adds their own topics to a summary (never AI-written, same guardrails and crisis handling); the clinician sees them only on a shared summary |
| **Reminders** | Calm in-app nudges (no notifications): an appointment tomorrow without a prepared summary, or yesterday's session without a note |
| **Data rights** | Clients can download all their data as JSON and permanently delete their account (password + typed confirmation); the audit log keeps only a content-free event |

**Multi-tenant B2B2C model:** clinic (organization) → clinicians → clients. Clinicians only see summaries their clients explicitly share; clinic admins see no clinical content at all.

## Engineering principles

- **The LLM is never an authorization mechanism.** Access control, data scoping and business rules are enforced by the backend; AI tools only receive data the current user is allowed to see.
- **Human-in-the-loop** for every AI output that leaves the client's account.
- **Validated AI output:** structured schemas, citation checks against real entries, forbidden-content guardrails (no diagnosis, no medication or treatment advice).
- **User-written text is untrusted input** (prompt-injection aware).
- **Organization-level data isolation**, covered by authorization tests.
- No sensitive content in logs or LLM traces.

## Tech stack

**Backend:** Python, FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL
**AI:** Pydantic AI, structured outputs, tool calling, guardrails, evaluation
**Frontend:** React, TypeScript, Tailwind CSS
**Ops:** Docker, GitHub Actions, Render
**Tooling:** uv, ruff, pytest, pre-commit, gitleaks

## Development setup

Requirements: [uv](https://docs.astral.sh/uv/), Docker, Git.

```bash
cp .env.example .env          # then set your own local POSTGRES_PASSWORD / DATABASE_URL
docker compose up -d db redis # PostgreSQL on localhost:5433 (+ a separate test database), Redis on 6380
cd backend
uv sync                       # installs Python 3.13 and dependencies
uv run pre-commit install     # secret scanning and lint checks before each commit
uv run alembic upgrade head   # apply migrations
uv run python -m app.seed     # synthetic demo clinics, users, entries, appointments
uv run uvicorn app.main:create_app --factory --reload
uv run pytest                 # runs against the `<db>_test` database
```

API docs: http://localhost:8000/docs (disabled in production). Health: `/health` (liveness), `/health/ready` (database).

> Authentication: `POST /api/v1/auth/login` returns short-lived access + refresh JWTs (`Authorization: Bearer ...`). There is no open sign-up: accounts are created from invitations (`POST /api/v1/invitations`, token returned in the response until e-mail delivery exists). `JWT_SECRET` is required (see `.env.example`). `python -m app.seed` prints a random password for the demo users unless `SEED_PASSWORD` is set.

Full stack in containers (db, redis, api with migrations, worker + beat): `docker compose up --build`, then http://localhost:8000/health. Non-root image with a liveness `HEALTHCHECK`; the worker uses the same image with another command.

### CI

`.github/workflows/ci.yml` runs on every push/PR: backend (Postgres + Redis services, `uv sync --frozen`, `alembic upgrade head`, `pytest`, `ruff`, `pip-audit`), frontend (`npm ci`, lint, tests, build, `npm audit --omit=dev --audit-level=high`) and a Docker image build.

### Deploying to Render + Supabase (~$7/month)

Cost-optimised layout for a demo: **one** paid Render instance, everything else on free tiers.

| Piece | Where | Plan |
|---|---|---|
| Frontend (static site, SPA rewrite) | Render | free |
| API **+ Celery worker + beat** in one container (`backend/start.sh`) | Render web service | Starter (512 MB) |
| Redis (rate limits, Celery broker) | Render Key Value | free |
| PostgreSQL | Supabase | free |

`start.sh` runs uvicorn and a **thread-pool** Celery worker (no forked children; LLM calls are I/O-bound) with embedded beat (stale-job reaper, expired refresh-token cleanup). If either process exits, the container exits and Render restarts it, so the API never keeps running with a dead worker. Measured locally under a 512 MB limit: ~410 MB idle (two Python processes of ~200 MB each), leaving ~100 MB headroom. `MALLOC_ARENA_MAX=2` limits growth from the worker's threads. Check the service's Metrics tab after deploy; if memory gets tight, set `CELERY_CONCURRENCY=1`. Locally, `docker compose` still runs API and worker as separate containers.

1. **Supabase:** create a project in region **Frankfurt (eu-central-1)**. *Connect → Session pooler* (IPv4, port `5432`) and copy the URI; append `?sslmode=require` (the app maps it to asyncpg's `ssl=require`). Do not use the direct connection (IPv6-only on the free plan) or the transaction pooler (port `6543`, breaks asyncpg prepared statements).
2. **Render:** dashboard → **New → Blueprint**, select the repo. Enter the `sync: false` values (table below). `CELERY_BROKER_URL` is wired automatically; `JWT_SECRET` is generated. Migrations run as the pre-deploy command.
3. **Circular URLs:** the frontend needs the API URL and the API needs the frontend origin. After the first sync, copy both public URLs and set `VITE_API_URL` (static site; then redeploy it, it is baked at build time) and `CORS_ORIGINS` (API).
4. Verify the production readiness list below.

| Variable | Service | Notes |
|---|---|---|
| `DATABASE_URL` | api | Supabase session-pooler URI + `?sslmode=require` |
| `ANTHROPIC_API_KEY` | api | without it AI endpoints answer 503 |
| `CORS_ORIGINS` | api | frontend origin, no wildcard, no trailing slash |
| `VITE_API_URL` | web | public API URL, `https://...` |
| `METRICS_TOKEN` | api | optional; blank = `/metrics` is 404 |
| `LOGFIRE_TOKEN` | api | optional; blank = tracing off |
| `SEED_PASSWORD`, `SEED_DEMO=1` | api (temporary) | only for the demo seed, see below |

Free-tier notes: Supabase pauses projects after a period of inactivity (beat's periodic jobs query the database, which normally keeps it active; a paused project is resumed from the Supabase dashboard). The pool is kept small (`DB_POOL_SIZE=3`, `DB_MAX_OVERFLOW=2`) for the pooler's connection limit.

### Demo accounts

Public sign-up stays closed. To load the synthetic demo clinics once, open a Shell on the API service (or add the two variables and a one-off job) and run:

```bash
SEED_DEMO=1 SEED_PASSWORD='<choose 12+ chars>' python -m app.seed
```

It refuses to run in production without both values, is idempotent (existing organizations are skipped) and writes only fictional data. Demo content is in Turkish, like the UI, and medication names are clearly fictional.

To restore the demo to a clean state (e.g. after many visitors), run the same command with `--reset`. It deletes **only** the two demo organizations (`demo-clinic`, `other-clinic`) and everything in them, including accounts created there by invitation, then re-seeds; audit logs are kept and a `demo_reset` record is added:

```bash
SEED_DEMO=1 SEED_PASSWORD='<choose 12+ chars>' python -m app.seed --reset
``` The password is never in the repo or printed. All demo users share it:

| Role | Login |
|---|---|
| Clinic admin | `admin@demo-clinic.test` |
| Clinician | `dr.elif@demo-clinic.test`, `dr.mert@demo-clinic.test` |
| Client | `client.ayse@demo-clinic.test`, `client.can@demo-clinic.test`, `client.zeynep@demo-clinic.test` |

Live demo: _link will be added after the first deploy_ (`https://<your-web>.onrender.com`). The login screen shows the synthetic-data warning.

### Production readiness checklist

- [ ] HTTPS only (Render terminates TLS; the static site and API URLs are `https://`).
- [ ] `/docs`, `/redoc` and `/openapi.json` are disabled (`APP_ENV=production`): check they return 404.
- [ ] `CORS_ORIGINS` lists only the frontend origin.
- [ ] Rate limiting runs on Redis (`RATE_LIMIT_BACKEND=redis`; the app refuses to start with `memory`); login returns 503 rather than skipping limits if Redis is down.
- [ ] `TRUSTED_PROXY_HOPS=1` verified: the app sees exactly one proxy hop, and the rightmost `X-Forwarded-For` entry is the real client IP (two different clients must not share a rate-limit bucket).
- [ ] LLM spend limit: per-user caps (`LLM_DAILY_REQUEST_LIMIT`, `LLM_DAILY_COST_LIMIT_USD`) plus a monthly spend limit set in the Anthropic console.
- [ ] `METRICS_TOKEN` set (or `/metrics` left unset = 404) and never in a URL.
- [ ] `SEED_DEMO` / `SEED_PASSWORD` removed after seeding; `JWT_SECRET` not shared with anything else.
- [ ] API logs show `celery ... ready` and beat started (same container); `/health/ready` is 200 (Supabase reachable).
- [ ] Memory stays under 512 MB under load (Render → Metrics).

### Evaluation, rate limiting and observability (Phase 5)

- **Offline AI evals** (`backend/evals/`, synthetic TR+EN data, enforced by `pytest tests/test_evals.py`): crisis detection (zero false negatives required), guardrail recall/false positives, prompt-injection attacks against a "model that obeys" (nothing may be stored), citation faithfulness. Report: `uv run python -m evals.offline` or `pytest -s tests/test_evals.py`. A paid, real-model evaluation exists as `uv run python -m evals.run_live --max-requests N`; it is never run by tests or CI.
- **Rate limits** (Redis; `429` + `Retry-After`): login (per IP and per account), refresh, invitation acceptance, summary generation, after-session notes, plus a per-user rolling 24h LLM request/cost budget from `llm_usage`. All limits are env-configurable (see `.env.example`). With `APP_ENV=production` the limiter must be Redis-backed (`memory` is rejected at startup) and the login/refresh/invitation scopes fail closed (`503` + `Retry-After`) if Redis is down.
- **Client IP behind a proxy:** set `TRUSTED_PROXY_HOPS` to the number of proxies you run (Render: `1`); the limiter then uses the Nth entry from the right of `X-Forwarded-For`, so a client-supplied header cannot dodge limits. `0` (default) ignores the header. In production the variable must be set explicitly (startup fails otherwise). After the first deploy, verify the value: send one request and check how many entries `X-Forwarded-For` has when it reaches the app (it must equal the number of proxies you trust; the rightmost N-th entry must be the real client IP). The container runs uvicorn with `--no-proxy-headers` so only this logic decides.
- **Accepted risk (invitations):** the invitation token is returned to the inviter (no e-mail delivery), so the inviter can tell from the accept step (400 vs 201) whether an e-mail is already registered in another organization. When e-mail delivery is added, remove the token from the API response.
- **Sessions:** refresh tokens rotate on every use (jti stored in `refresh_tokens`); replaying a used token revokes the whole session family; `POST /api/v1/auth/logout` revokes it; sessions end `SESSION_MAX_DAYS` (30) after login.
- **Sharing:** a clinician sees a shared summary only if it was shared after their assignment began; a newly assigned clinician sees older summaries only after the client shares them again.
- **Observability:** `X-Request-ID` in/out (also carried into Celery job logs), JSON logs without content, `/metrics` (Prometheus text; 404 unless `METRICS_TOKEN` is set), stale `running` job reaper (Celery beat, `--beat` in the compose worker).
- **LLM tracing:** Logfire, enabled only when `LOGFIRE_TOKEN` is set, with content export disabled (only span names, timings, model and token counts). Logfire was chosen over LangSmith because Pydantic AI instruments natively through OpenTelemetry (no extra SDK in the call path) and content exclusion is a single setting; LangSmith's stronger prompt/dataset management is not needed because evals run offline in pytest.

### Backend layout

```
backend/app/
  api/        HTTP routes and dependencies (session, current user)
  core/       settings, database, JSON logging, request-ID middleware
  models/     SQLAlchemy models: Organization, User, Entry, Appointment
  schemas/    Pydantic request/response models (per-kind entry details)
  services/   business logic, every query scoped to owner + organization
  seed.py     synthetic demo data
backend/alembic/   migrations
backend/tests/     API, isolation, migration and seed tests (real PostgreSQL)
```

## License

Copyright © 2026. All rights reserved. The source is public for review; no license is granted for reuse.

## Frontend

`frontend/`: React + TypeScript + Vite + Tailwind CSS (Turkish UI).

```bash
cd frontend
cp .env.example .env     # VITE_API_URL, default http://localhost:8000
npm ci && npm run dev    # http://localhost:5173
npm run lint && npm test -- --run && npm run build
```

Backend side: set `CORS_ORIGINS=http://localhost:5173` in the repo-root `.env` (empty by default; wildcards are rejected).

- **Tokens:** the access token is kept in memory only. The backend does not issue cookies, so the refresh token is stored in `sessionStorage` (cleared when the tab closes) and is used to restore the session after a reload. On a 401 the client refreshes once and retries; if that fails the user is logged out. Tokens are never put in URLs.
- **Not built (no backend endpoint yet):** appointments and "My plan".
- Invitations: e-mail delivery does not exist, so the one-time invitation code is shown to the inviter, who passes it on; the invitee pastes it on the "Accept invitation" page.
