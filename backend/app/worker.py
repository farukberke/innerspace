"""Celery application and tasks. Start a worker with:
    celery -A app.worker worker --loglevel=INFO

Embed the scheduler (stale-job reaper) with `-B`, or run `celery -A app.worker beat` apart.

Task arguments are a job id and the originating request ID only; results are never stored
(`ignore_result`), so neither the broker nor a result backend ever sees content."""

import asyncio
import logging
import time
import uuid

from celery import Celery

from app.ai.llm import AiUnavailableError, build_model
from app.core.config import Settings, get_settings
from app.core.db import create_engine, create_sessionmaker
from app.core.logging import configure_logging, request_id_var
from app.core.middleware import new_request_id
from app.core.tracing import configure_tracing
from app.services import auth, jobs

_settings = get_settings()
configure_logging(_settings.log_level)
configure_tracing(_settings)
logger = logging.getLogger("app.worker")

celery_app = Celery("innerspace", broker=_settings.celery_broker_url)
celery_app.conf.update(
    task_ignore_result=True,
    task_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "reap-stale-summary-jobs": {
            "task": "summary_jobs.reap_stale",
            "schedule": float(_settings.job_reaper_interval_seconds),
        },
        "purge-expired-refresh-tokens": {
            "task": "auth.purge_expired_refresh_tokens",
            "schedule": float(_settings.refresh_purge_interval_seconds),
        },
    },
)


async def _process(settings: Settings, job_id: uuid.UUID, final_attempt: bool) -> jobs.JobOutcome:
    engine = create_engine(settings)
    try:
        async with create_sessionmaker(engine)() as session:
            try:
                model = build_model(settings)
            except AiUnavailableError:
                await jobs.fail_queued(session, job_id, "ai_unavailable")
                return jobs.JobOutcome.DONE
            return await jobs.run(session, settings, model, job_id, final_attempt=final_attempt)
    finally:
        await engine.dispose()


@celery_app.task(
    bind=True,
    name="summary_jobs.generate",
    max_retries=_settings.job_max_retries,
    ignore_result=True,
)
def generate_summary_job(self, job_id: str, request_id: str | None = None) -> None:  # noqa: ANN001
    # Carry the originating request's correlation ID into the job's logs.
    token = request_id_var.set(new_request_id(request_id))
    started = time.perf_counter()
    try:
        final_attempt = self.request.retries >= self.max_retries
        outcome = asyncio.run(_process(_settings, uuid.UUID(job_id), final_attempt))
        logger.info(
            "summary_job",
            extra={
                "job_id": job_id,
                "outcome": outcome.value,
                "attempt": self.request.retries + 1,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
    finally:
        request_id_var.reset(token)
    if outcome is jobs.JobOutcome.RETRY:
        # Exponential backoff: base, 2x base, 4x base, ...
        countdown = _settings.job_retry_backoff_seconds * 2**self.request.retries
        raise self.retry(countdown=countdown)


async def _reap(settings: Settings) -> list[uuid.UUID]:
    engine = create_engine(settings)
    try:
        async with create_sessionmaker(engine)() as session:
            return await jobs.reap_stale(
                session, settings.job_stale_after_seconds, settings.job_max_retries + 1
            )
    finally:
        await engine.dispose()


@celery_app.task(name="summary_jobs.reap_stale", ignore_result=True)
def reap_stale_jobs() -> None:
    for job_id in asyncio.run(_reap(_settings)):
        enqueue_summary_job(job_id)


async def _purge_refresh_tokens(settings: Settings) -> int:
    engine = create_engine(settings)
    try:
        async with create_sessionmaker(engine)() as session:
            return await auth.purge_expired_refresh_tokens(session)
    finally:
        await engine.dispose()


@celery_app.task(name="auth.purge_expired_refresh_tokens", ignore_result=True)
def purge_expired_refresh_tokens() -> None:
    deleted = asyncio.run(_purge_refresh_tokens(_settings))
    logger.info("refresh_tokens_purged", extra={"deleted": deleted})


def enqueue_summary_job(job_id: uuid.UUID) -> None:
    generate_summary_job.apply_async(args=[str(job_id), request_id_var.get()])
