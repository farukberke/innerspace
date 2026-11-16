"""Minimal in-process metrics in the Prometheus text format (no content, low cardinality:
labels are route templates, status codes and fixed names, never user input)."""

import threading
from collections import defaultdict

BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self.latency_buckets: dict[tuple[str, str, float], int] = defaultdict(int)
        self.latency_sum: dict[tuple[str, str], float] = defaultdict(float)
        self.latency_count: dict[tuple[str, str], int] = defaultdict(int)
        self.errors: dict[str, int] = defaultdict(int)
        self.llm_calls: dict[tuple[str, str], int] = defaultdict(int)
        self.llm_tokens: dict[tuple[str, str], int] = defaultdict(int)
        self.llm_cost_usd: float = 0.0

    def observe_request(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self.requests[(method, route, status)] += 1
            self.latency_sum[(method, route)] += seconds
            self.latency_count[(method, route)] += 1
            for bound in BUCKETS:
                if seconds <= bound:
                    self.latency_buckets[(method, route, bound)] += 1

    def observe_error(self, error_code: str) -> None:
        with self._lock:
            self.errors[error_code] += 1

    def observe_llm(
        self, purpose: str, success: bool, input_tokens: int, output_tokens: int, cost: float
    ) -> None:
        with self._lock:
            self.llm_calls[(purpose, "ok" if success else "error")] += 1
            self.llm_tokens[(purpose, "input")] += input_tokens
            self.llm_tokens[(purpose, "output")] += output_tokens
            self.llm_cost_usd += cost

    def render(self) -> str:
        lines: list[str] = ["# TYPE http_requests_total counter"]
        with self._lock:
            for (method, route, status), n in sorted(self.requests.items()):
                labels = f'method="{method}",route="{route}",status="{status}"'
                lines.append(f"http_requests_total{{{labels}}} {n}")
            lines.append("# TYPE http_request_duration_seconds histogram")
            for (method, route), count in sorted(self.latency_count.items()):
                base = f'method="{method}",route="{route}"'
                for bound in BUCKETS:
                    n = self.latency_buckets.get((method, route, bound), 0)
                    lines.append(f'http_request_duration_seconds_bucket{{{base},le="{bound}"}} {n}')
                lines.append(f'http_request_duration_seconds_bucket{{{base},le="+Inf"}} {count}')
                total = self.latency_sum[(method, route)]
                lines.append(f"http_request_duration_seconds_sum{{{base}}} {total:.6f}")
                lines.append(f"http_request_duration_seconds_count{{{base}}} {count}")
            lines.append("# TYPE app_errors_total counter")
            for code, n in sorted(self.errors.items()):
                lines.append(f'app_errors_total{{error_code="{code}"}} {n}')
            lines.append("# TYPE llm_calls_total counter")
            for (purpose, outcome), n in sorted(self.llm_calls.items()):
                lines.append(f'llm_calls_total{{purpose="{purpose}",outcome="{outcome}"}} {n}')
            lines.append("# TYPE llm_tokens_total counter")
            for (purpose, kind), n in sorted(self.llm_tokens.items()):
                lines.append(f'llm_tokens_total{{purpose="{purpose}",type="{kind}"}} {n}')
            lines.append("# TYPE llm_cost_usd_total counter")
            lines.append(f"llm_cost_usd_total {self.llm_cost_usd:.6f}")
        return "\n".join(lines) + "\n"


METRICS = Metrics()
