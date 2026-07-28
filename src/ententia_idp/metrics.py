import time
from prometheus_client import Counter, Histogram, CollectorRegistry, generate_latest


registry = CollectorRegistry()

requests_total = Counter(
    "ententia_idp_requests_total",
    "Total number of document processing requests",
    registry=registry,
)

request_latency_seconds = Histogram(
    "ententia_idp_request_latency_seconds",
    "Request latency in seconds",
    registry=registry,
)

agent_latency_seconds = Histogram(
    "ententia_idp_agent_latency_seconds",
    "Latency per agent in seconds",
    ["agent_name"],
    registry=registry,
)

agent_errors_total = Counter(
    "ententia_idp_agent_errors_total",
    "Total number of agent failures",
    ["agent_name"],
    registry=registry,
)

agent_token_usage_total = Counter(
    "ententia_idp_agent_tokens_total",
    "Total token usage per agent",
    ["agent_name", "direction"],
    registry=registry,
)


def get_metrics() -> bytes:
    return generate_latest(registry)


class AgentMetricTracker:
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.start_time = time.perf_counter()
        self.end_time = None
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0
        self.error = None

    def finish(self, input_tokens: int = 0, output_tokens: int = 0, cost_usd: float = 0.0, error: str | None = None):
        self.end_time = time.perf_counter()
        duration = self.end_time - self.start_time
        agent_latency_seconds.labels(agent_name=self.agent_name).observe(duration)
        if input_tokens:
            agent_token_usage_total.labels(agent_name=self.agent_name, direction="input").inc(input_tokens)
        if output_tokens:
            agent_token_usage_total.labels(agent_name=self.agent_name, direction="output").inc(output_tokens)
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cost_usd = cost_usd
        self.error = error
        if error:
            agent_errors_total.labels(agent_name=self.agent_name).inc()

    def to_dict(self):
        return {
            "agent_name": self.agent_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "latency_seconds": self.end_time - self.start_time if self.end_time else None,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "error": self.error,
        }
