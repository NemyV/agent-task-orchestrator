from dataclasses import dataclass


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    message: str


class DeterministicVerifier:
    def verify(self, goal: str, output: str) -> VerificationResult:
        if not output.strip():
            return VerificationResult(False, "verification failed: execution produced no output")
        normalized_goal = " ".join(goal.split())
        if normalized_goal not in output:
            return VerificationResult(
                False,
                "verification failed: output did not reference bounded goal",
            )
        return VerificationResult(True, "verified: output present and bounded goal preserved")
