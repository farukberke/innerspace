"""Offline evals that need no database and no LLM. Run: `uv run python -m evals.offline`.
(The same numbers are enforced, with thresholds, by `tests/test_evals.py`.)"""

from evals.metrics import crisis_metrics, format_report, guardrail_metrics


def main() -> None:
    metrics, missed = crisis_metrics()
    print(format_report("crisis_detection", metrics))  # noqa: T201
    for text in missed:
        print(f"  MISSED CRISIS: {text!r}")  # noqa: T201
    metrics, missed = guardrail_metrics()
    print(format_report("guardrails", metrics))  # noqa: T201
    for text in missed:
        print(f"  MISSED FORBIDDEN: {text!r}")  # noqa: T201


if __name__ == "__main__":
    main()
