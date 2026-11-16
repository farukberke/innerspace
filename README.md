# InnerSpace

**A between-sessions notebook for people in therapy or psychiatric care.** Clients log what happens between appointments, and an AI assistant helps them turn their own entries into a short, source-cited summary they review, approve and choose to share with their clinician.

> [!WARNING]
> **Portfolio / demo project.** InnerSpace uses **synthetic data only**. It is not a medical device, does not diagnose, and does not provide treatment or crisis support. Do not enter real personal or health information.
> If you are in crisis, contact your local emergency number (112 in Türkiye).

## Status

🚧 **Active development.** Phase 1 (backend foundation) is complete; Phase 2 (authentication & authorization) is next.

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 | Repository, tooling, secret scanning | ✅ Done |
| 1 | FastAPI app, PostgreSQL, SQLAlchemy models, Alembic, entry CRUD, structured logging | ✅ Done |
| 2 | JWT auth, roles, RBAC, organization-level isolation, authorization tests | ⏭ Next |
| 3 | AI summaries: structured output, citations, guardrails, human-in-the-loop sharing | |
| 4 | Background jobs (Redis, Celery), retries, idempotency | |
| 5 | AI evaluation, rate limiting, observability, LLM tracing | |
| 6 | Docker, CI/CD, AWS deployment | |
| — | React + TypeScript frontend, built alongside the backend | |

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

> Phase 1 has no authentication yet: requests act as the seeded user in `DEV_USER_EMAIL`. This is disabled in production and replaced by JWT authentication in Phase 2.

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
