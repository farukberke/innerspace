"""Celery application and tasks. Start a worker with:
    celery -A app.worker worker --loglevel=INFO

Task arguments are a job id only; results are never stored (`ignore_result`), so neither the
broker nor a result backend ever sees content."""

import asyncio
import uuid

from celery import Celery

from app.ai.llm import AiUnavailableError, build_model
from app.core.config import Settings, get_settings
from app.core.db import create_engine, create_sessionmaker
from app.core.logging import configure_logging
from app.services import jobs

_settings = get_settings()
configure_logging(_settings.log_level)

celery_app = Celery("innerspace", broker=_settings.celery_broker_url)
celery_app.conf.update(
    task_ignore_result=True,
    task_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
)


async def _process(settings: Settings, job_id: uuid.UUID, final_attempt: bool) -> jobs.JobOutcome:
    engine = create_engine(settings.database_url)
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
def generate_summary_job(self, job_id: str) -> None:  # noqa: ANN001
    final_attempt = self.request.retries >= self.max_retries
    outcome = asyncio.run(_process(_settings, uuid.UUID(job_id), final_attempt))
    if outcome is jobs.JobOutcome.RETRY:
        # Exponential backoff: base, 2x base, 4x base, ...
        countdown = _settings.job_retry_backoff_seconds * 2**self.request.retries
        raise self.retry(countdown=countdown)


def enqueue_summary_job(job_id: uuid.UUID) -> None:
    generate_summary_job.apply_async(args=[str(job_id)])
