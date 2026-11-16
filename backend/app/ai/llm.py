"""LLM access: building the model from settings, usage/cost accounting, safe error mapping."""

import time
import uuid
from decimal import Decimal

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage, UsageLimits
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import LlmUsage, User


class AiUnavailableError(Exception):
    """No usable LLM configuration (missing API key or unsupported provider)."""


class AiGenerationError(Exception):
    """The model failed, or never produced output that passed validation and guardrails."""


def build_model(settings: Settings) -> Model:
    provider, _, name = settings.llm_model.partition(":")
    if provider != "anthropic" or not name:
        raise AiUnavailableError("unsupported LLM provider")
    if settings.anthropic_api_key is None:
        raise AiUnavailableError("LLM API key is not configured")
    return AnthropicModel(
        name, provider=AnthropicProvider(api_key=settings.anthropic_api_key.get_secret_value())
    )


def _cost(settings: Settings, usage: RunUsage) -> Decimal:
    cost = (
        usage.input_tokens * settings.llm_input_usd_per_mtok
        + usage.output_tokens * settings.llm_output_usd_per_mtok
    ) / 1_000_000
    return Decimal(str(round(cost, 6)))


async def run_agent[DepsT, OutT](
    session: AsyncSession,
    settings: Settings,
    model: Model,
    user: User,
    purpose: str,
    agent: Agent[DepsT, OutT],
    prompt: str,
    deps: DepsT,
) -> OutT:
    """Runs an agent, always records token/cost/latency (success or failure) and maps every
    failure to AiGenerationError. Neither prompt nor output is stored or logged."""
    usage = RunUsage()
    started = time.perf_counter()
    success = False
    try:
        result = await agent.run(
            prompt,
            model=model,
            deps=deps,
            usage=usage,
            retries=settings.llm_max_retries,
            model_settings=ModelSettings(timeout=settings.llm_timeout_seconds, max_tokens=4000),
            usage_limits=UsageLimits(request_limit=6 + 3 * settings.llm_max_retries),
        )
        success = True
        return result.output
    except Exception as exc:
        raise AiGenerationError(type(exc).__name__) from None
    finally:
        session.add(
            LlmUsage(
                id=uuid.uuid4(),
                organization_id=user.organization_id,
                user_id=user.id,
                purpose=purpose,
                model=model.model_name[:100],
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                requests=usage.requests,
                cost_usd=_cost(settings, usage),
                duration_ms=int((time.perf_counter() - started) * 1000),
                success=success,
            )
        )
        await session.commit()
