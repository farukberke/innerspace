# InnerSpace

**A between-sessions notebook for people in therapy or psychiatric care.** Clients log what happens between appointments, and an AI assistant helps them turn their own entries into a short, source-cited summary they review, approve and choose to share with their clinician.

> [!WARNING]
> **Portfolio / demo project.** InnerSpace uses **synthetic data only**. It is not a medical device, does not diagnose, and does not provide treatment or crisis support. Do not enter real personal or health information.
> If you are in crisis, contact your local emergency number (112 in Türkiye).

## Status

🚧 **Active development.** Phases 1 (backend foundation), 2 (authentication & authorization), 3 (AI summaries), 4 (background jobs), 5 (evaluation, rate limiting, observability) and the React frontend are complete; Phase 6 is next.

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 | Repository, tooling, secret scanning | ✅ Done |
| 1 | FastAPI app, PostgreSQL, SQLAlchemy models, Alembic, entry CRUD, structured logging | ✅ Done |
| 2 | JWT auth, roles, RBAC, organization-level isolation, authorization tests | ✅ Done |
| 3 | AI summaries: structured output, citations, guardrails, human-in-the-loop sharing | ✅ Done |
| 4 | Background jobs (Redis, Celery), retries, idempotency | ✅ Done |
| 5 | AI evaluation, rate limiting, observability, LLM tracing | ✅ Done |
| 6 | Docker, CI/CD, Render deployment | ⏭ Next |
| — | React + TypeScript frontend, built alongside the backend | ✅ Done (client, clinician and clinic-admin screens) |

## What it does (planned v1)

| | |
|---|---|
| **Log** | Quick entries, panic episode logs, medication & side-effect notes, avoidance notes |
| **Prepare** | AI-assisted pre-appointment summary — every statement links back to the client's own entries |
| **Review & share** | Nothing leaves the client's account without explicit approval; sharing is revocable |
| **After session** | Short note structured into "what we discussed / what I'll try / questions for next time" |
| **My plan** | Support plan authored with the clinician, available in difficult moments |

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
**Ops:** Docker, GitHub Actions, AWS
**Tooling:** uv, ruff, pytest, pre-commit, gitleaks

## Development setup

Requirements: [uv](https://docs.astral.sh/uv/), Docker, Git.

```bash
cp .env.example .env          # then set your own local POSTGRES_PASSWORD / DATABASE_URL
docker compose up -d          # PostgreSQL on localhost:5433 (+ a separate test database)
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

### Evaluation, rate limiting and observability (Phase 5)

- **Offline AI evals** (`backend/evals/`, synthetic TR+EN data, enforced by `pytest tests/test_evals.py`): crisis detection (zero false negatives required), guardrail recall/false positives, prompt-injection attacks against a "model that obeys" (nothing may be stored), citation faithfulness. Report: `uv run python -m evals.offline` or `pytest -s tests/test_evals.py`. A paid, real-model evaluation exists as `uv run python -m evals.run_live --max-requests N`; it is never run by tests or CI.
- **Rate limits** (Redis; `429` + `Retry-After`): login (per IP and per account), refresh, invitation acceptance, summary generation, after-session notes, plus a per-user rolling 24h LLM request/cost budget from `llm_usage`. All limits are env-configurable (see `.env.example`). With `APP_ENV=production` the limiter must be Redis-backed (`memory` is rejected at startup) and the login/refresh/invitation scopes fail closed (`503` + `Retry-After`) if Redis is down.
- **Client IP behind a proxy:** set `TRUSTED_PROXY_HOPS` to the number of proxies you run (Render: `1`); the limiter then uses the Nth entry from the right of `X-Forwarded-For`, so a client-supplied header cannot dodge limits. `0` (default) ignores the header. The container runs uvicorn with `--no-proxy-headers` so only this logic decides.
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
