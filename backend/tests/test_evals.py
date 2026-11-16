"""Offline AI evaluations (synthetic data only, no real model). They print a metric report
(`pytest -s tests/test_evals.py` to see it) and FAIL when a metric drops below its threshold."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from evals import run_live
from evals.datasets.crisis import CRISIS_NEGATIVE, CRISIS_POSITIVE
from evals.datasets.guardrails import ALLOWED, FORBIDDEN
from evals.datasets.injection import ATTACKS, BEHAVIOURS
from evals.flows import CITATION_CASES, run_faithfulness, run_injection
from evals.metrics import (
    CRISIS_MAX_FALSE_NEGATIVES,
    CRISIS_MAX_FALSE_POSITIVE_RATE,
    FAITHFULNESS_MIN_FABRICATION_REJECTION,
    FAITHFULNESS_MIN_VALID_ACCEPTANCE,
    GUARDRAIL_MAX_FALSE_POSITIVE_RATE,
    GUARDRAIL_MIN_RECALL,
    INJECTION_MAX_ATTACK_SUCCESS_RATE,
    crisis_metrics,
    format_report,
    guardrail_metrics,
)


def test_datasets_are_bilingual_and_large_enough() -> None:
    assert len(CRISIS_POSITIVE) >= 40 and len(CRISIS_NEGATIVE) >= 35
    assert len(FORBIDDEN) >= 30 and len(ALLOWED) >= 20
    assert {a.behaviour for a in ATTACKS} == set(BEHAVIOURS)  # every behaviour is exercised
    assert any("istiyorum" in t for t in CRISIS_POSITIVE)
    assert any("want to die" in t for t in CRISIS_POSITIVE)


def test_crisis_detection_never_misses_a_labelled_crisis() -> None:
    metrics, missed = crisis_metrics()
    print(format_report("crisis_detection", metrics))
    assert metrics["fn"] == CRISIS_MAX_FALSE_NEGATIVES, f"missed crisis texts: {missed}"
    assert metrics["false_positive_rate"] <= CRISIS_MAX_FALSE_POSITIVE_RATE


def test_guardrails_catch_forbidden_content_without_blocking_factual_text() -> None:
    metrics, missed = guardrail_metrics()
    print(format_report("guardrails", metrics))
    assert metrics["recall"] >= GUARDRAIL_MIN_RECALL, f"missed forbidden texts: {missed}"
    assert metrics["false_positive_rate"] <= GUARDRAIL_MAX_FALSE_POSITIVE_RATE


async def test_prompt_injection_obeyed_by_the_model_still_stores_nothing(
    db_session: AsyncSession, test_settings: Settings
) -> None:
    result = await run_injection(db_session, test_settings)
    print(format_report("prompt_injection", {k: v for k, v in result.items() if k != "failures"}))
    assert result["attacks"] >= 15
    assert result["attack_success_rate"] <= INJECTION_MAX_ATTACK_SUCCESS_RATE, result["failures"]
    assert result["failures"] == []


async def test_citation_faithfulness_rejects_fabricated_and_accepts_correct(
    db_session: AsyncSession, test_settings: Settings
) -> None:
    result = await run_faithfulness(db_session, test_settings)
    print(format_report("faithfulness", {k: v for k, v in result.items() if k != "wrong"}))
    assert result["cases"] == len(CITATION_CASES)
    assert result["fabrication_rejection_rate"] >= FAITHFULNESS_MIN_FABRICATION_REJECTION
    assert result["valid_acceptance_rate"] >= FAITHFULNESS_MIN_VALID_ACCEPTANCE
    assert result["stored_citations_out_of_scope"] == 0, result["wrong"]
    assert result["wrong"] == []


# --- Live eval script: never contacts a model in tests ---------------------------------


def test_live_eval_exits_with_a_clear_message_without_api_key(
    monkeypatch: pytest.MonkeyPatch, test_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    assert test_settings.anthropic_api_key is None
    monkeypatch.setattr(run_live, "get_settings", lambda: test_settings)
    assert run_live.main(["--max-requests", "3"]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_live_eval_rejects_a_non_positive_request_cap(
    monkeypatch: pytest.MonkeyPatch, test_settings: Settings
) -> None:
    monkeypatch.setattr(run_live, "get_settings", lambda: test_settings)
    monkeypatch.setattr(run_live, "build_model", lambda _s: object())  # never used
    assert run_live.main(["--max-requests", "0"]) == 2
