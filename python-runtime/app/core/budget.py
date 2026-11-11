"""Budget tracking and enforcement for AgentForge Core."""
import time

from app.contracts.run import BudgetSpec, Totals


class BudgetExceededError(Exception):
    """Raised when a run budget limit is exceeded."""
    pass


class BudgetTracker:
    """Tracks token usage, call counts, cost, and execution duration against BudgetSpec."""

    def __init__(self, spec: BudgetSpec):
        self.spec = spec
        self.start_time = time.time()
        self.totals = Totals()

    def check_request(self, messages, tools=None, max_output_tokens: int = 0) -> None:
        """Reject oversized prompts before sending them to a provider."""
        prompt_chars = len(str(messages)) + len(str(tools or []))
        estimated_input = (prompt_chars + 2) // 3
        if estimated_input > 12_000:
            raise BudgetExceededError(
                f"LLM prompt safety limit exceeded (estimated {estimated_input:,} input tokens). "
                "Reduce retrieved context or conversation history before retrying."
            )
        projected = self.totals.input_tokens + self.totals.output_tokens + estimated_input + max(0, max_output_tokens)
        if self.spec.max_total_tokens is not None and projected > self.spec.max_total_tokens:
            raise BudgetExceededError(
                f"LLM request blocked before provider call: estimated usage {projected:,} "
                f"would exceed the {self.spec.max_total_tokens:,}-token run budget."
            )
        self.check_limits()

    def record_llm_call(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cost_usd: float | None = None,
    ) -> None:
        self.totals.llm_calls += 1
        self.totals.input_tokens += input_tokens
        self.totals.output_tokens += output_tokens
        self.totals.cache_read_tokens += cache_read_tokens
        if cost_usd is not None:
            current_cost = self.totals.cost_usd or 0.0
            self.totals.cost_usd = current_cost + cost_usd

        self.check_limits()

    def record_tool_call(self) -> None:
        self.totals.tool_calls += 1

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    def check_limits(self) -> None:
        if self.spec.max_llm_calls is not None and self.totals.llm_calls > self.spec.max_llm_calls:
            raise BudgetExceededError(
                f"LLM call count budget exceeded ({self.totals.llm_calls} > {self.spec.max_llm_calls})"
            )

        total_tokens = self.totals.input_tokens + self.totals.output_tokens
        if self.spec.max_total_tokens is not None and total_tokens > self.spec.max_total_tokens:
            raise BudgetExceededError(
                f"Token count budget exceeded ({total_tokens} > {self.spec.max_total_tokens})"
            )

        if self.spec.max_cost_usd is not None and self.totals.cost_usd is not None:
            if self.totals.cost_usd > self.spec.max_cost_usd:
                raise BudgetExceededError(
                    f"Cost budget exceeded (${self.totals.cost_usd:.4f} > ${self.spec.max_cost_usd:.4f})"
                )

        if self.spec.max_seconds is not None and self.elapsed_seconds > self.spec.max_seconds:
            raise BudgetExceededError(
                f"Time budget exceeded ({self.elapsed_seconds:.1f}s > {self.spec.max_seconds}s)"
            )
