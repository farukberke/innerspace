"""Observability and reliability: request/correlation IDs (HTTP and Celery jobs), structured
error logs, /metrics, Logfire tracing (no-op without token, never exports content), stale-job
reaper, DB pool settings, indexes. Nothing here may log or export user-written content."""

import io
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from pydantic_ai import Agent
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app import worker
from app.core import tracing
from app.core.config import Settings
from app.core.db import create_engine
from app.core.logging import JsonFormatter, request_id_var
from app.core.metrics import METRICS
from app.models import SummaryJob, SummaryJobStatus, User
from app.services import ai, jobs
from tests.conftest import TEST_JWT_SECRET, FakeLlm, FakeQueue
from tests.test_ai import API, MARKER, PERIOD, Script, World, draft
from tests.test_ai import w as ai_world

w = ai_world  # shared world fixture, re-exported so pytest finds it here


class JsonLogs:
    """Captures what the real JSON formatter would print for the given loggers."""

    def __init__(self, *names: str) -> None:
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(JsonFormatter())
        self.loggers = [logging.getLogger(n) for n in names]

    def __enter__(self) -> "JsonLogs":
        for logger in self.loggers:
            logger.addHandler(self.handler)
            logger.setLevel(logging.DEBUG)
        return self

    def __exit__(self, *exc: object) -> None:
        for logger in self.loggers:
            logger.removeHandler(self.handler)

    @property
    def lines(self) -> list[dict]:
        return [json.loads(line) for line in self.stream.getvalue().splitlines() if line]


# --- Request ID ------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/health", "/nope", f"{API}/auth/me", "/metrics"])
async def test_every_response_carries_a_request_id(http: AsyncClient, path: str) -> None:
    response = await http.get(path)
    rid = response.headers["X-Request-ID"]
    assert rid and len(rid) <= 64
    assert response.headers["X-Request-ID"] != (await http.get(path)).headers["X-Request-ID"]


@pytest.mark.parametrize("incoming", ["abc-123_DEF.4", "a" * 64, uuid.uuid4().hex])
async def test_safe_incoming_request_id_is_kept(http: AsyncClient, incoming: str) -> None:
    response = await http.get("/health", headers={"X-Request-ID": incoming})
    assert response.headers["X-Request-ID"] == incoming


@pytest.mark.parametrize(
    "incoming",
    ["a" * 65, "has space", "semi;colon", "new\tline", "<script>x</script>", "x/../y", " "],
)
async def test_unsafe_incoming_request_id_is_replaced(http: AsyncClient, incoming: str) -> None:
    response = await http.get("/health", headers={"X-Request-ID": incoming})
    rid = response.headers["X-Request-ID"]
    assert rid != incoming and len(rid) == 32 and rid.isalnum()


async def test_request_log_carries_request_id_and_route_but_no_query(http: AsyncClient) -> None:
    with JsonLogs("app.request") as logs:
        await http.get(f"/health?q={MARKER}", headers={"X-Request-ID": "trace-42"})
    (line,) = logs.lines
    assert line["request_id"] == "trace-42" and line["path"] == "/health"
    assert line["status"] == 200 and line["route"] == "/health"
    assert MARKER not in json.dumps(line)


async def test_unhandled_errors_log_code_and_request_id_without_content(
    http: AsyncClient,
) -> None:
    app = http._transport.app  # type: ignore[attr-defined]

    async def boom() -> None:
        raise RuntimeError(f"database said: {MARKER}")

    app.add_api_route("/_boom", boom)
    with JsonLogs("app.request") as logs:
        response = await http.get("/_boom", headers={"X-Request-ID": "err-1"})
    assert response.status_code == 500
    body = response.json()
    assert body == {
        "detail": "Internal server error",
        "error_code": "internal_error",
        "request_id": "err-1",
    }
    assert response.headers["X-Request-ID"] == "err-1"
    error = next(line for line in logs.lines if line["msg"] == "unhandled_error")
    assert error["error_code"] == "internal_error" and error["request_id"] == "err-1"
    assert error["error_type"] == "RuntimeError" and "test_observability.py" in error["location"]
    assert MARKER not in json.dumps(logs.lines) and "exc_info" not in error
    assert MARKER not in response.text


# --- Metrics ---------------------------------------------------------------------------


async def test_metrics_is_disabled_without_a_token(http: AsyncClient) -> None:
    assert (await http.get("/metrics")).status_code == 404


async def test_metrics_requires_the_bearer_token(
    http: AsyncClient, monkeypatch: pytest.MonkeyPatch, test_settings: Settings
) -> None:
    monkeypatch.setattr(test_settings, "metrics_token", SecretStr("m" * 24))
    assert (await http.get("/metrics")).status_code == 401
    assert (await http.get("/metrics", headers={"Authorization": "Bearer nope"})).status_code == 401
    assert (await http.get("/metrics", headers={"Authorization": "m" * 24})).status_code == 401
    ok = await http.get("/metrics", headers={"Authorization": f"Bearer {'m' * 24}"})
    assert ok.status_code == 200 and ok.headers["content-type"].startswith("text/plain")


async def test_metrics_report_latency_errors_and_llm_usage_without_content(
    http: AsyncClient,
    acting,
    llm: FakeLlm,
    w: World,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
) -> None:
    monkeypatch.setattr(test_settings, "metrics_token", SecretStr("m" * 24))
    METRICS.reset()
    acting.user = w.client
    entry_id = w.own_entries[0].id
    await http.get(f"{API}/entries/{entry_id}")  # a templated route with an ID in the path
    await http.get("/does-not-exist")
    llm.model = Script(lambda ids: draft(ids[0], text=f"Kayit {MARKER} ozeti")).model
    await ai.generate_summary(db_session, test_settings, llm.model, w.client, *_period_dates())
    acting.user = None
    text = (await http.get("/metrics", headers={"Authorization": f"Bearer {'m' * 24}"})).text
    assert 'route="/entries/{entry_id}"' in text
    assert str(entry_id) not in text  # templates only: no IDs, no cardinality blow-up
    assert 'route="unmatched"' in text and "/does-not-exist" not in text
    assert 'http_request_duration_seconds_bucket{method="GET"' in text
    assert 'llm_calls_total{purpose="session_summary",outcome="ok"} 1' in text
    assert 'llm_tokens_total{purpose="session_summary",type="input"}' in text
    assert MARKER not in text


def _period_dates():
    from datetime import date  # noqa: PLC0415

    return date(2026, 11, 1), date(2026, 11, 15)


# --- Celery: correlation ID in job logs ------------------------------------------------


def test_enqueue_passes_the_current_request_id_to_the_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(worker.generate_summary_job, "apply_async", lambda **kw: calls.append(kw))
    job_id = uuid.uuid4()
    token = request_id_var.set("req-77")
    try:
        worker.enqueue_summary_job(job_id)
    finally:
        request_id_var.reset(token)
    assert calls == [{"args": [str(job_id), "req-77"]}]


@pytest.mark.parametrize(
    ("sent", "expect_kept"), [("req-77", True), ("bad id!", False), (None, False)]
)
def test_job_logs_carry_the_originating_request_id(
    monkeypatch: pytest.MonkeyPatch, sent: str | None, expect_kept: bool
) -> None:
    seen: list[str | None] = []

    async def fake_process(settings, job_id, final_attempt):  # noqa: ANN001
        seen.append(request_id_var.get())
        return jobs.JobOutcome.DONE

    monkeypatch.setattr(worker, "_process", fake_process)
    job_id = uuid.uuid4()
    with JsonLogs("app.worker") as logs:
        worker.generate_summary_job.apply(args=[str(job_id), sent])
    (line,) = logs.lines
    assert line["msg"] == "summary_job" and line["job_id"] == str(job_id)
    assert line["outcome"] == "done" and line["attempt"] == 1 and "duration_ms" in line
    assert line["request_id"] == seen[0]
    assert (seen[0] == sent) is expect_kept and len(seen[0]) <= 64
    assert request_id_var.get() is None  # the context does not leak between tasks


# --- Stale job reaper ------------------------------------------------------------------


async def _job(
    session: AsyncSession,
    client: User,
    status: SummaryJobStatus,
    *,
    age: int,
    attempts: int,
    day: int,
    end_day: int | None = None,
) -> SummaryJob:
    job = SummaryJob(
        organization_id=client.organization_id,
        client_id=client.id,
        period_start=datetime(2026, 11, day, tzinfo=UTC).date(),
        period_end=datetime(2026, 11, end_day or day, tzinfo=UTC).date(),
        status=status,
        attempts=attempts,
    )
    session.add(job)
    await session.flush()
    await session.execute(
        update(SummaryJob)
        .where(SummaryJob.id == job.id)
        .values(updated_at=datetime.now(UTC) - timedelta(seconds=age))
    )
    return job


async def test_reaper_requeues_or_fails_stale_running_jobs_and_is_idempotent(
    db_session: AsyncSession, w: World
) -> None:
    running = SummaryJobStatus.RUNNING
    retryable = await _job(db_session, w.client, running, age=3600, attempts=1, day=1)
    exhausted = await _job(db_session, w.client, running, age=3600, attempts=4, day=2)
    fresh = await _job(db_session, w.client, running, age=10, attempts=1, day=3)
    old_queued = await _job(
        db_session, w.client, SummaryJobStatus.QUEUED, age=3600, attempts=0, day=4
    )
    old_done = await _job(
        db_session, w.client, SummaryJobStatus.SUCCEEDED, age=3600, attempts=1, day=5
    )

    requeued = await jobs.reap_stale(db_session, 900, max_attempts=4)
    assert requeued == [retryable.id]  # only this one must be enqueued again

    async def state(job: SummaryJob) -> tuple[SummaryJobStatus, str | None]:
        row = await db_session.scalar(
            select(SummaryJob)
            .where(SummaryJob.id == job.id)
            .execution_options(populate_existing=True)
        )
        return row.status, row.error_code

    assert await state(retryable) == (SummaryJobStatus.QUEUED, None)
    assert await state(exhausted) == (SummaryJobStatus.FAILED, "stale_timeout")
    assert await state(fresh) == (running, None)
    assert await state(old_queued) == (SummaryJobStatus.QUEUED, None)
    assert await state(old_done) == (SummaryJobStatus.SUCCEEDED, None)
    # A second run finds nothing: re-queued jobs are no longer `running`.
    assert await jobs.reap_stale(db_session, 900, max_attempts=4) == []
    assert await state(exhausted) == (SummaryJobStatus.FAILED, "stale_timeout")


async def test_reaped_job_can_be_claimed_and_finished_by_a_worker(
    db_session: AsyncSession, acting, llm: FakeLlm, w: World, test_settings: Settings
) -> None:
    await _job(
        db_session, w.client, SummaryJobStatus.RUNNING, age=3600, attempts=1, day=1, end_day=15
    )
    [job_id] = await jobs.reap_stale(db_session, 900, max_attempts=4)
    llm.model = Script(lambda ids: draft(ids[0])).model
    outcome = await jobs.run(db_session, test_settings, llm.model, job_id, final_attempt=False)
    assert outcome is jobs.JobOutcome.DONE
    done = await db_session.scalar(
        select(SummaryJob).where(SummaryJob.id == job_id).execution_options(populate_existing=True)
    )
    assert done.status == SummaryJobStatus.SUCCEEDED and done.attempts == 2


def test_reaper_task_enqueues_requeued_jobs_and_is_scheduled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = [uuid.uuid4(), uuid.uuid4()]
    enqueued: list[uuid.UUID] = []

    async def fake_reap(_settings):  # noqa: ANN001
        return ids

    monkeypatch.setattr(worker, "_reap", fake_reap)
    monkeypatch.setattr(worker, "enqueue_summary_job", enqueued.append)
    worker.reap_stale_jobs.apply()
    assert enqueued == ids
    schedule = worker.celery_app.conf.beat_schedule["reap-stale-summary-jobs"]
    assert schedule["task"] == "summary_jobs.reap_stale" and schedule["schedule"] >= 5


# --- DB pool and indexes ---------------------------------------------------------------


def test_db_pool_settings_come_from_the_environment_settings() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        jwt_secret=TEST_JWT_SECRET,
        db_pool_size=3,
        db_max_overflow=1,
        db_pool_timeout_seconds=7,
        db_pool_recycle_seconds=60,
    )
    pool = create_engine(settings).sync_engine.pool
    assert (pool.size(), pool._max_overflow, pool._timeout, pool._recycle) == (3, 1, 7, 60)


async def test_indexes_for_hot_queries_exist(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        found = await conn.run_sync(
            lambda sync_conn: {
                (table, ix["name"])
                for table in ("llm_usage", "summary_jobs", "entries", "summaries")
                for ix in __import__("sqlalchemy").inspect(sync_conn).get_indexes(table)
            }
        )
    assert ("llm_usage", "ix_llm_usage_user_id_created_at") in found  # daily budget
    assert ("summary_jobs", "ix_summary_jobs_running_updated_at") in found  # reaper
    assert ("entries", "ix_entries_client_id_occurred_at") in found
    assert ("summaries", "ix_summaries_client_id_created_at") in found


# --- Tracing (Logfire) -----------------------------------------------------------------


def test_tracing_is_a_no_op_without_a_token(test_settings: Settings) -> None:
    assert test_settings.logfire_token is None
    assert tracing.configure_tracing(test_settings) is False
    blank = test_settings.model_copy(update={"logfire_token": SecretStr("")})
    assert tracing.configure_tracing(blank) is False


def test_instrumentation_settings_exclude_content() -> None:
    settings = tracing.instrumentation_settings()
    assert settings.include_content is False and settings.include_binary_content is False


def test_tracing_with_a_token_configures_logfire_without_content(
    monkeypatch: pytest.MonkeyPatch, test_settings: Settings
) -> None:
    import logfire  # noqa: PLC0415

    configured: list[dict] = []
    instrumented: list[object] = []
    monkeypatch.setattr(logfire, "configure", lambda **kw: configured.append(kw))
    monkeypatch.setattr(Agent, "instrument_all", staticmethod(instrumented.append))
    enabled = test_settings.model_copy(update={"logfire_token": SecretStr("lf-test-token")})
    assert tracing.configure_tracing(enabled) is True
    (kwargs,) = configured
    assert kwargs["token"] == "lf-test-token" and kwargs["console"] is False  # noqa: S105
    assert kwargs["send_to_logfire"] is True and kwargs["inspect_arguments"] is False
    (settings,) = instrumented
    assert settings.include_content is False and settings.include_binary_content is False


def _span_dump(exporter) -> str:
    return json.dumps(
        [
            {
                "name": s.name,
                "attributes": dict(s.attributes or {}),
                "events": [
                    {"name": e.name, "attributes": dict(e.attributes or {})} for e in s.events
                ],
            }
            for s in exporter.get_finished_spans()
        ],
        default=str,
    )


async def _traced_summary(db_session, test_settings, w, include_content: bool):
    from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: PLC0415
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: PLC0415
        InMemorySpanExporter,
    )
    from pydantic_ai.agent import InstrumentationSettings  # noqa: PLC0415

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    if include_content:
        settings = InstrumentationSettings(tracer_provider=provider, include_content=True)
    else:
        settings = tracing.instrumentation_settings(tracer_provider=provider)
    Agent.instrument_all(settings)
    try:
        script = Script(lambda ids: draft(ids[0], text=f"Kayit {MARKER} ozeti"))
        await ai.generate_summary(
            db_session, test_settings, script.model, w.client, *_period_dates()
        )
    finally:
        Agent.instrument_all(False)
    return _span_dump(exporter)


async def test_exported_spans_never_contain_prompts_tool_results_or_records(
    db_session: AsyncSession, test_settings: Settings, w: World
) -> None:
    dump = await _traced_summary(db_session, test_settings, w, include_content=False)
    assert "invoke_agent" in dump or "agent run" in dump  # spans really were produced
    assert "function-model" in dump or "function:" in dump  # model name is kept
    for secret in (MARKER, "slept badly", "walked outside", "Seans oncesi ozet", "entries_data"):
        assert secret not in dump, secret


async def test_negative_control_content_is_visible_when_content_is_enabled(
    db_session: AsyncSession, test_settings: Settings, w: World
) -> None:
    dump = await _traced_summary(db_session, test_settings, w, include_content=True)
    assert MARKER in dump  # proves the check above can detect a leak


# --- Extended "no content in logs" check over the new code paths -----------------------


async def test_no_content_in_any_log_metric_or_error_body_across_new_paths(
    http: AsyncClient,
    acting,
    llm: FakeLlm,
    w: World,
    jobq: FakeQueue,
    db_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
) -> None:
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(test_settings, "rate_limit_generate", "1/hour")
    monkeypatch.setattr(test_settings, "metrics_token", SecretStr("m" * 24))
    llm.model = Script(lambda ids: draft(ids[0], text=f"Kayit {MARKER} ozeti")).model
    acting.user = w.client
    first = await http.post(f"{API}/summaries/generate", json=PERIOD)
    limited = await http.post(f"{API}/summaries/generate", json=PERIOD)
    assert (first.status_code, limited.status_code) == (202, 429)
    await jobs.run(db_session, test_settings, llm.model, jobq.ids[0], final_attempt=False)
    await http.post(f"{API}/after-session-notes", json={"text": f"not {MARKER}"})
    await http.post(f"{API}/auth/login", json={"email": f"{MARKER}@x.test", "password": MARKER})
    metrics = await http.get("/metrics", headers={"Authorization": f"Bearer {'m' * 24}"})
    for text in (
        caplog.text,
        limited.text,
        metrics.text,
        "".join(r.getMessage() for r in caplog.records),
    ):
        assert MARKER not in text
    assert MARKER.lower() not in caplog.text.lower()
