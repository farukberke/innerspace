# Deployment and operations

Details moved out of the README. Layout: one Render web service (API + Celery worker + beat), a Render static site and Render Key Value (Redis), with PostgreSQL on Supabase.

## Deploying to Render + Supabase (~$7/month)

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

## Demo accounts

Public sign-up stays closed. To load the synthetic demo clinics once, open a Shell on the API service (or add the two variables and a one-off job) and run:

```bash
SEED_DEMO=1 SEED_PASSWORD='<choose 12+ chars>' python -m app.seed
```

It refuses to run in production without both values, is idempotent (existing organizations are skipped) and writes only fictional data. Demo content is in Turkish, like the UI, and medication names are clearly fictional.

To restore the demo to a clean state (e.g. after many visitors), run the same command with `--reset`. It deletes **only** the two demo organizations (`demo-clinic`, `other-clinic`) and everything in them, including accounts created there by invitation, then re-seeds; audit logs are kept and a `demo_reset` record is added:

```bash
SEED_DEMO=1 SEED_PASSWORD='<choose 12+ chars>' python -m app.seed --reset
```

The password is never in the repo or printed. All demo users share it:

| Role | Login |
|---|---|
| Clinic admin | `admin@demo-clinic.test` |
| Clinician | `dr.elif@demo-clinic.test`, `dr.mert@demo-clinic.test` |
| Client | `client.ayse@demo-clinic.test`, `client.can@demo-clinic.test`, `client.zeynep@demo-clinic.test` |

Live demo: https://innerspace-web.onrender.com. The login screen shows the synthetic-data warning.

## Production readiness checklist

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

## Evaluation, rate limiting and observability (Phase 5)

- **Offline AI evals** (`backend/evals/`, synthetic TR+EN data, enforced by `pytest tests/test_evals.py`): crisis detection (zero false negatives required), guardrail recall/false positives, prompt-injection attacks against a "model that obeys" (nothing may be stored), citation faithfulness. Report: `uv run python -m evals.offline` or `pytest -s tests/test_evals.py`. A paid, real-model evaluation exists as `uv run python -m evals.run_live --max-requests N`; it is never run by tests or CI.
- **Rate limits** (Redis; `429` + `Retry-After`): login (per IP and per account), refresh, invitation acceptance, summary generation, after-session notes, plus a per-user rolling 24h LLM request/cost budget from `llm_usage`. All limits are env-configurable (see `.env.example`). With `APP_ENV=production` the limiter must be Redis-backed (`memory` is rejected at startup) and the login/refresh/invitation scopes fail closed (`503` + `Retry-After`) if Redis is down.
- **Client IP behind a proxy:** set `TRUSTED_PROXY_HOPS` to the number of proxies you run (Render: `1`); the limiter then uses the Nth entry from the right of `X-Forwarded-For`, so a client-supplied header cannot dodge limits. `0` (default) ignores the header. In production the variable must be set explicitly (startup fails otherwise). After the first deploy, verify the value: send one request and check how many entries `X-Forwarded-For` has when it reaches the app (it must equal the number of proxies you trust; the rightmost N-th entry must be the real client IP). The container runs uvicorn with `--no-proxy-headers` so only this logic decides.
- **Accepted risk (invitations):** the invitation token is returned to the inviter (no e-mail delivery), so the inviter can tell from the accept step (400 vs 201) whether an e-mail is already registered in another organization. When e-mail delivery is added, remove the token from the API response.
- **Sessions:** refresh tokens rotate on every use (jti stored in `refresh_tokens`); replaying a used token revokes the whole session family; `POST /api/v1/auth/logout` revokes it; sessions end `SESSION_MAX_DAYS` (30) after login.
- **Sharing:** a clinician sees a shared summary only if it was shared after their assignment began; a newly assigned clinician sees older summaries only after the client shares them again.
- **Observability:** `X-Request-ID` in/out (also carried into Celery job logs), JSON logs without content, `/metrics` (Prometheus text; 404 unless `METRICS_TOKEN` is set), stale `running` job reaper (Celery beat, `--beat` in the compose worker).
- **LLM tracing:** Logfire, enabled only when `LOGFIRE_TOKEN` is set, with content export disabled (only span names, timings, model and token counts). Logfire was chosen over LangSmith because Pydantic AI instruments natively through OpenTelemetry (no extra SDK in the call path) and content exclusion is a single setting; LangSmith's stronger prompt/dataset management is not needed because evals run offline in pytest.
