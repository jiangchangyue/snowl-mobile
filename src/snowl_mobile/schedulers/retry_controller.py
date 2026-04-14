from __future__ import annotations

from dataclasses import dataclass

from snowl_mobile.core.policies import RetryPolicy
from snowl_mobile.core.trial_state_machine import TrialState


@dataclass(frozen=True, slots=True)
class TrialFailure:
    error_type: str
    message: str
    retryable: bool | None = None


@dataclass(frozen=True, slots=True)
class RetryDecision:
    should_retry: bool
    retryable: bool
    max_attempts: int
    next_attempt: int | None
    reason: str


class RetryController:
    def __init__(self, policy: RetryPolicy) -> None:
        self.policy = policy

    @property
    def max_attempts(self) -> int:
        return self.policy.max_trial_retries + 1

    def classify_failure(self, error_type: str, message: str) -> TrialFailure:
        return TrialFailure(
            error_type=error_type,
            message=message,
            retryable=error_type in self.policy.retry_on,
        )

    def should_retry(self, trial_state: TrialState, failure: TrialFailure) -> RetryDecision:
        retryable = (
            failure.retryable
            if failure.retryable is not None
            else failure.error_type in self.policy.retry_on
        )
        if not retryable:
            return RetryDecision(
                should_retry=False,
                retryable=False,
                max_attempts=self.max_attempts,
                next_attempt=None,
                reason=f"error type '{failure.error_type}' is not retryable",
            )
        if trial_state.attempt_count >= self.max_attempts:
            return RetryDecision(
                should_retry=False,
                retryable=True,
                max_attempts=self.max_attempts,
                next_attempt=None,
                reason="retry budget exhausted",
            )
        return RetryDecision(
            should_retry=True,
            retryable=True,
            max_attempts=self.max_attempts,
            next_attempt=trial_state.attempt_count + 1,
            reason=f"retryable failure '{failure.error_type}' within retry budget",
        )
