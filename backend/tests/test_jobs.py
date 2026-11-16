"""Background summary jobs: 202 + status polling, idempotency (also under concurrency), atomic
claiming, retry rules, crisis, authorization and privacy. No Redis: the queue is a fake that
records job ids, and jobs are run explicitly with `jobs.run` (what the Celery task calls)."""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import (
    LlmUsage,
    Organization,
    Summary,
    SummaryJob,
    SummaryJobStatus,
    User,
    UserRole,
)
from app.services import jobs
from app.services.jobs import JobOutcome
from tests.conftest import FakeLlm, FakeQueue
from tests.test_ai import (
    API,
    IN_RANGE,
    MARKER,
    PERIOD,
    Script,
    World,
    _entry,
    draft,
)
from tests.test_ai import w as ai_world

w = ai_world  # the shared fixture, re-exported so pytest finds it here
GEN = f"{API}/summaries/generate"


async def _post(http: AsyncClient, acting, user: User, llm: FakeLlm, script=None, **kw):
    acting.user = user
    llm.model = (script or Script(draft())).model
    return await http.post(GEN, json=PERIOD, **kw)


async def _run(session, settings, llm: FakeLlm, job_id: str, *, final: bool = False):
    return await jobs.run(session, settings, llm.model, uuid.UUID(job_id), final_attempt=final)


# --- Happy path ------------------------------------------------------------------------


async def test_generate_returns_202_and_job_then_worker_succeeds(
    http: AsyncClient, acting, llm: FakeLlm, w: World, jobq: FakeQueue, db_session: AsyncSession
) -> None:
    script = Script(lambda ids: draft(ids[0]))
    response = await _post(http, acting, w.client, llm, script)
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["status"] == "queued" and job["summary_id"] is None and job["attempts"] == 0
    assert jobq.ids == [uuid.UUID(job["id"])]
    assert script.requests == 0  # nothing is generated inside the request
    assert (await db_session.scalar(select(func.count()).select_from(Summary))) == 0

    assert await _run(db_session, acting.settings, llm, job["id"]) is JobOutcome.DONE
    done = (await http.get(f"{API}/summaries/jobs/{job['id']}")).json()
    assert done["status"] == "succeeded" and done["attempts"] == 1 and done["error_code"] is None
    summary = (await http.get(f"{API}/summaries/{done['summary_id']}")).json()
    assert summary["status"] == "draft"  # still private, still needs the client's approval


# --- Idempotency -----------------------------------------------------------------------


async def test_same_idempotency_key_returns_one_job(
    http: AsyncClient, acting, llm: FakeLlm, w: World, jobq: FakeQueue, db_session: AsyncSession
) -> None:
    headers = {"Idempotency-Key": "abc-123"}
    first = await _post(http, acting, w.client, llm, headers=headers)
    second = await _post(http, acting, w.client, llm, headers=headers)
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert len(jobq.ids) == 1  # enqueued once
    assert (await db_session.scalar(select(func.count()).select_from(SummaryJob))) == 1
    # Another key is a different request; reusing a key with other parameters is a conflict.
    other = await _post(http, acting, w.client, llm, headers={"Idempotency-Key": "zzz"})
    assert other.json()["id"] != first.json()["id"]
    changed = await http.post(
        GEN,
        json={"period_start": "2026-11-02", "period_end": "2026-11-15"},
        headers=headers,
    )
    assert changed.status_code == 409


async def test_keys_are_scoped_per_client(
    http: AsyncClient, acting, llm: FakeLlm, w: World
) -> None:
    headers = {"Idempotency-Key": "shared-key"}
    a = await _post(http, acting, w.client, llm, headers=headers)
    b = await _post(http, acting, w.client_same_org, llm, headers=headers)
    assert a.json()["id"] != b.json()["id"]


async def test_without_key_active_job_for_same_period_is_reused(
    http: AsyncClient, acting, llm: FakeLlm, w: World, db_session: AsyncSession
) -> None:
    first = await _post(http, acting, w.client, llm)
    again = await _post(http, acting, w.client, llm)
    assert first.json()["id"] == again.json()["id"]
    # Once finished, a new request is a new job (the user may want a fresh draft).
    await _run(db_session, acting.settings, llm, first.json()["id"])
    fresh = await _post(http, acting, w.client, llm)
    assert fresh.json()["id"] != first.json()["id"]


@pytest.mark.parametrize("key", ["x" * 129, "has space", ""])
async def test_invalid_idempotency_key_is_rejected(
    http: AsyncClient, acting, llm: FakeLlm, w: World, key: str
) -> None:
    response = await _post(http, acting, w.client, llm, headers={"Idempotency-Key": key})
    assert response.status_code == 422


@pytest.fixture
async def committed_client(
    engine: AsyncEngine, password_hash: str
) -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], User]]:
    """A client committed for real (no rollback wrapper), so concurrent sessions can race."""
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        org = Organization(slug=f"race-{uuid.uuid4().hex[:8]}", name="race (test)")
        session.add(org)
        await session.flush()
        client = User(
            organization_id=org.id,
            email=f"c@{org.slug}.test",
            display_name="c",
            role=UserRole.CLIENT,
            password_hash=password_hash,
        )
        session.add(client)
        await session.commit()
    yield maker, client
    async with maker() as session:
        await session.execute(Organization.__table__.delete().where(Organization.id == org.id))
        await session.commit()


@pytest.mark.parametrize("key", ["race-key", None])
async def test_concurrent_requests_create_a_single_job(committed_client, key) -> None:
    from datetime import date

    maker, client = committed_client

    async def attempt() -> tuple[uuid.UUID, bool]:
        async with maker() as session:
            job, created = await jobs.create_or_get(
                session, client, date(2026, 11, 1), date(2026, 11, 15), key
            )
            return job.id, created

    results = await asyncio.gather(*(attempt() for _ in range(6)))
    assert len({job_id for job_id, _ in results}) == 1
    assert sum(created for _, created in results) == 1
    async with maker() as session:
        count = await session.scalar(
            select(func.count()).select_from(SummaryJob).where(SummaryJob.client_id == client.id)
        )
    assert count == 1


async def test_concurrent_workers_claim_a_job_once(committed_client) -> None:
    from datetime import date

    maker, client = committed_client
    async with maker() as session:
        job, _ = await jobs.create_or_get(
            session, client, date(2026, 11, 1), date(2026, 11, 15), None
        )

    async def claim() -> bool:
        async with maker() as session:
            return await jobs._claim(session, job.id) is not None

    wins = await asyncio.gather(*(claim() for _ in range(6)))
    assert sum(wins) == 1
    async with maker() as session:
        assert (await session.get(SummaryJob, job.id)).attempts == 1


# --- Worker: no double processing ------------------------------------------------------


async def test_running_a_job_twice_creates_one_summary(
    http: AsyncClient, acting, llm: FakeLlm, w: World, db_session: AsyncSession
) -> None:
    script = Script(lambda ids: draft(ids[0]))
    job_id = (await _post(http, acting, w.client, llm, script)).json()["id"]
    assert await _run(db_session, acting.settings, llm, job_id) is JobOutcome.DONE
    requests = script.requests
    assert await _run(db_session, acting.settings, llm, job_id) is JobOutcome.SKIPPED
    assert script.requests == requests  # the model was not called again
    assert (await db_session.scalar(select(func.count()).select_from(Summary))) == 1
    assert (await db_session.scalar(select(func.count()).select_from(LlmUsage))) == 1


async def test_job_already_running_is_not_started_again(
    http: AsyncClient, acting, llm: FakeLlm, w: World, db_session: AsyncSession
) -> None:
    job_id = (await _post(http, acting, w.client, llm)).json()["id"]
    await db_session.execute(
        update(SummaryJob).values(status=SummaryJobStatus.RUNNING)  # another worker has it
    )
    assert await _run(db_session, acting.settings, llm, job_id) is JobOutcome.SKIPPED
    assert (await db_session.scalar(select(func.count()).select_from(Summary))) == 0


# --- Retry rules -----------------------------------------------------------------------


def _failing(exc: Exception) -> FunctionModel:
    def fail(messages: list[ModelMessage], info: AgentInfo):
        raise exc

    return FunctionModel(fail)


@pytest.mark.parametrize(
    "exc",
    [ModelHTTPError(503, "m"), ModelHTTPError(429, "m"), ModelHTTPError(500, "m"), TimeoutError()],
)
async def test_transient_error_requeues_then_succeeds(
    http: AsyncClient, acting, llm: FakeLlm, w: World, db_session: AsyncSession, exc: Exception
) -> None:
    job_id = (await _post(http, acting, w.client, llm)).json()["id"]
    llm.model = _failing(exc)
    assert await _run(db_session, acting.settings, llm, job_id) is JobOutcome.RETRY
    job = (await http.get(f"{API}/summaries/jobs/{job_id}")).json()
    assert job["status"] == "queued" and job["error_code"] is None and job["attempts"] == 1
    # The retry delivery works once the provider is back; attempts are counted.
    llm.model = Script(lambda ids: draft(ids[0])).model
    assert await _run(db_session, acting.settings, llm, job_id) is JobOutcome.DONE
    job = (await http.get(f"{API}/summaries/jobs/{job_id}")).json()
    assert job["status"] == "succeeded" and job["attempts"] == 2


async def test_transient_error_on_final_attempt_fails_with_code(
    http: AsyncClient, acting, llm: FakeLlm, w: World, db_session: AsyncSession
) -> None:
    job_id = (await _post(http, acting, w.client, llm)).json()["id"]
    llm.model = _failing(ModelHTTPError(503, "m"))
    outcome = await _run(db_session, acting.settings, llm, job_id, final=True)
    assert outcome is JobOutcome.DONE
    job = (await http.get(f"{API}/summaries/jobs/{job_id}")).json()
    assert job["status"] == "failed" and job["error_code"] == "ai_unavailable"


@pytest.mark.parametrize(
    "exc", [ModelHTTPError(400, "m"), ModelHTTPError(401, "m"), ValueError("boom")]
)
async def test_permanent_provider_error_is_not_retried(
    http: AsyncClient, acting, llm: FakeLlm, w: World, db_session: AsyncSession, exc: Exception
) -> None:
    job_id = (await _post(http, acting, w.client, llm)).json()["id"]
    llm.model = _failing(exc)
    assert await _run(db_session, acting.settings, llm, job_id) is JobOutcome.DONE
    job = (await http.get(f"{API}/summaries/jobs/{job_id}")).json()
    assert job["status"] == "failed" and job["error_code"] == "generation_failed"
    assert job["attempts"] == 1


async def test_guardrail_exhaustion_fails_without_retry(
    http: AsyncClient, acting, llm: FakeLlm, w: World, db_session: AsyncSession
) -> None:
    script = Script(draft(w.own_entries[0].id, text="You have an anxiety disorder."))
    job_id = (await _post(http, acting, w.client, llm, script)).json()["id"]
    assert await _run(db_session, acting.settings, llm, job_id) is JobOutcome.DONE
    job = (await http.get(f"{API}/summaries/jobs/{job_id}")).json()
    assert job["status"] == "failed" and job["error_code"] == "generation_failed"
    assert script.output_attempts == 3
    assert (await db_session.scalar(select(func.count()).select_from(Summary))) == 0
    assert await _run(db_session, acting.settings, llm, job_id) is JobOutcome.SKIPPED


async def test_empty_period_fails_with_validation_code(
    http: AsyncClient, acting, llm: FakeLlm, w: World, db_session: AsyncSession
) -> None:
    acting.user = w.client
    llm.model = Script(draft()).model
    body = {"period_start": "2025-01-01", "period_end": "2025-01-10"}
    job_id = (await http.post(GEN, json=body)).json()["id"]
    assert await _run(db_session, acting.settings, llm, job_id) is JobOutcome.DONE
    job = (await http.get(f"{API}/summaries/jobs/{job_id}")).json()
    assert job["status"] == "failed" and job["error_code"] == "validation_failed"


async def test_inactive_client_job_fails(
    http: AsyncClient, acting, llm: FakeLlm, w: World, db_session: AsyncSession
) -> None:
    script = Script(draft())
    job_id = (await _post(http, acting, w.client, llm, script)).json()["id"]
    w.client.is_active = False
    await db_session.flush()
    assert await _run(db_session, acting.settings, llm, job_id) is JobOutcome.DONE
    job = await db_session.get(SummaryJob, uuid.UUID(job_id), populate_existing=True)
    assert job.status == SummaryJobStatus.FAILED and job.error_code == "client_inactive"
    assert script.requests == 0


async def test_celery_task_retries_with_backoff_then_gives_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The task wiring: RETRY outcomes are retried up to max_retries, the last run is final."""
    from app import worker

    calls: list[bool] = []

    async def fake_process(settings: Settings, job_id: uuid.UUID, final_attempt: bool):
        calls.append(final_attempt)
        return JobOutcome.DONE if final_attempt else JobOutcome.RETRY

    monkeypatch.setattr(worker, "_process", fake_process)
    task = worker.generate_summary_job
    await asyncio.to_thread(task.apply, args=[str(uuid.uuid4())])  # eager: runs in this process
    assert calls == [False] * task.max_retries + [True]
    assert task.ignore_result is True


async def test_celery_task_does_not_retry_when_done(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import worker

    process = AsyncMock(return_value=JobOutcome.DONE)
    monkeypatch.setattr(worker, "_process", process)
    await asyncio.to_thread(worker.generate_summary_job.apply, args=[str(uuid.uuid4())])
    assert process.await_count == 1


# --- Crisis ----------------------------------------------------------------------------


async def test_crisis_job_status_and_fixed_response_without_llm(
    http: AsyncClient, acting, llm: FakeLlm, w: World, db_session: AsyncSession
) -> None:
    await _entry(db_session, w.client, IN_RANGE, "Bazen kendimi öldürmek istiyorum")
    script = Script(draft(w.own_entries[0].id))
    job_id = (await _post(http, acting, w.client, llm, script)).json()["id"]
    assert await _run(db_session, acting.settings, llm, job_id) is JobOutcome.DONE
    job = (await http.get(f"{API}/summaries/jobs/{job_id}")).json()
    assert job["status"] == "crisis" and job["summary_id"] is None
    assert (
        job["crisis"]["crisis"] is True and job["crisis"]["message"] and job["crisis"]["resources"]
    )
    assert script.requests == 0
    assert (await db_session.scalar(select(func.count()).select_from(LlmUsage))) == 0
    assert (await db_session.scalar(select(func.count()).select_from(Summary))) == 0


# --- Authorization and isolation -------------------------------------------------------


async def test_job_status_is_visible_only_to_the_owning_client(
    http: AsyncClient, acting, llm: FakeLlm, w: World
) -> None:
    job_id = (await _post(http, acting, w.client, llm)).json()["id"]
    url = f"{API}/summaries/jobs/{job_id}"
    assert (await http.get(url)).status_code == 200
    for other in (w.client_same_org, w.client_other_org):
        acting.user = other
        assert (await http.get(url)).status_code == 404
    for clinician in (w.clinician, w.clinician_other_org):
        acting.user = clinician
        assert (await http.get(url)).status_code == 403
    acting.user = None
    assert (await http.get(url)).status_code == 401
    acting.user = w.client
    assert (await http.get(f"{API}/summaries/jobs/{uuid.uuid4()}")).status_code == 404


async def test_org_admin_and_clinician_cannot_create_or_read_jobs(
    http: AsyncClient, acting, llm: FakeLlm, w: World, make_user, org_a: Organization
) -> None:
    admin = await make_user(org_a, UserRole.ORG_ADMIN, "adm")
    job_id = (await _post(http, acting, w.client, llm)).json()["id"]
    for user in (admin, w.clinician):
        acting.user = user
        assert (await http.post(GEN, json=PERIOD)).status_code == 403
        assert (await http.get(f"{API}/summaries/jobs/{job_id}")).status_code == 403


async def test_inactive_user_cannot_use_job_endpoints(
    http: AsyncClient, acting, llm: FakeLlm, w: World, db_session: AsyncSession
) -> None:
    job_id = (await _post(http, acting, w.client, llm)).json()["id"]
    w.client.is_active = False
    await db_session.flush()
    assert (await http.get(f"{API}/summaries/jobs/{job_id}")).status_code == 401
    assert (await http.post(GEN, json=PERIOD)).status_code == 401


async def test_no_api_key_means_503_and_no_job(
    http: AsyncClient, acting, w: World, db_session: AsyncSession, jobq: FakeQueue
) -> None:
    acting.user = w.client  # llm.model unset: no key configured
    assert (await http.post(GEN, json=PERIOD)).status_code == 503
    assert (await db_session.scalar(select(func.count()).select_from(SummaryJob))) == 0
    assert jobq.ids == []


async def test_enqueue_failure_marks_job_failed_and_returns_503(
    http: AsyncClient, acting, llm: FakeLlm, w: World, db_session: AsyncSession, jobq: FakeQueue
) -> None:
    jobq.broken = True
    response = await _post(http, acting, w.client, llm)
    assert response.status_code == 503
    job = await db_session.scalar(select(SummaryJob))
    assert job.status == SummaryJobStatus.FAILED and job.error_code == "enqueue_failed"
    # A later request is not blocked by the dead job.
    jobq.broken = False
    assert (await _post(http, acting, w.client, llm)).status_code == 202


# --- Privacy ---------------------------------------------------------------------------


async def test_jobs_and_logs_hold_no_content(
    http: AsyncClient,
    acting,
    llm: FakeLlm,
    w: World,
    db_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    script = Script(lambda ids: draft(ids[0], text=f"Kayit {MARKER} ozeti"))
    response = await _post(http, acting, w.client, llm, script)
    job_id = response.json()["id"]
    await _run(db_session, acting.settings, llm, job_id)
    polled = await http.get(f"{API}/summaries/jobs/{job_id}")
    assert MARKER not in response.text and MARKER not in polled.text
    assert MARKER not in caplog.text
    columns = {c.name for c in SummaryJob.__table__.columns}
    assert columns.isdisjoint({"prompt", "content", "text", "output", "body", "note", "error"})
    # Failures expose only a code, never exception text.
    llm.model = FunctionModel(lambda m, i: (_ for _ in ()).throw(ValueError(f"leak {MARKER}")))
    failed_id = (await http.post(GEN, json={**PERIOD, "period_end": "2026-11-14"})).json()["id"]
    await _run(db_session, acting.settings, llm, failed_id)
    failed = await http.get(f"{API}/summaries/jobs/{failed_id}")
    assert failed.json()["error_code"] == "generation_failed" and MARKER not in failed.text
    assert MARKER not in caplog.text
