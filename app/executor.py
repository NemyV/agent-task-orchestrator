from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionResult:
    output: str


class DeterministicExecutor:
    """Safe portfolio executor used to demonstrate orchestration without external API keys."""

    def execute(self, goal: str) -> ExecutionResult:
        normalized = " ".join(goal.split())
        return ExecutionResult(output=f"Executed bounded task: {normalized}")
