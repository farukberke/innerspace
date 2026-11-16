"""LLM tracing with Logfire (Pydantic AI's native instrumentation).

Off unless LOGFIRE_TOKEN is set. Content is NEVER exported: prompts, tool arguments/results,
model output and record text are excluded; spans carry only names, timings, model and token
counts. Only Pydantic AI is instrumented (no HTTP/FastAPI/DB instrumentation, whose payloads or
URLs could carry content).
"""

import logging
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.agent import InstrumentationSettings

from app.core.config import Settings

logger = logging.getLogger(__name__)


def instrumentation_settings(**kwargs: Any) -> InstrumentationSettings:
    return InstrumentationSettings(include_content=False, include_binary_content=False, **kwargs)


def configure_tracing(settings: Settings) -> bool:
    """Returns True when tracing was enabled."""
    if settings.logfire_token is None or not settings.logfire_token.get_secret_value():
        return False
    import logfire  # noqa: PLC0415  (only imported when tracing is on)

    logfire.configure(
        token=settings.logfire_token.get_secret_value(),
        service_name="innerspace",
        environment=settings.app_env,
        send_to_logfire=True,
        console=False,
        inspect_arguments=False,
    )
    Agent.instrument_all(instrumentation_settings())
    logger.info("llm tracing enabled")
    return True
