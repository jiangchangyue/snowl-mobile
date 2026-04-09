from __future__ import annotations

from dataclasses import dataclass, field

from snowl_mobile.core.errors import StateTransitionError
from snowl_mobile.core.states import TrialStatus
from snowl_mobile.core.trial_spec import TrialSpec
from snowl_mobile.schemas.base import SchemaModel


@dataclass(frozen=True, slots=True)
class TrialTransition(SchemaModel):
    from_status: str
    to_status: str
    event: str
    reason: str = ""


@dataclass(slots=True)
class TrialState(SchemaModel):
    spec: TrialSpec
    status: TrialStatus
    attempt_count: int = 0
    max_attempts: int = 1
    last_error_type: str | None = None
    last_error_message: str | None = None
    history: list[TrialTransition] = field(default_factory=list)

    @property
    def trial_id(self) -> str:
        return self.spec.trial_id

    @property
    def can_retry(self) -> bool:
        return self.attempt_count < self.max_attempts

    def to_summary(self) -> dict[str, object]:
        return {
            "trial_id": self.spec.trial_id,
            "agent_id": self.spec.agent_id,
            "benchmark_id": self.spec.benchmark_id,
            "model_id": self.spec.model_id,
            "seed": self.spec.seed,
            "status": self.status.value,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "last_error_type": self.last_error_type,
            "last_error_message": self.last_error_message,
            "history": [transition.to_dict() for transition in self.history],
        }


class TrialStateMachine:
    _ALLOWED_TRANSITIONS: dict[TrialStatus, set[TrialStatus]] = {
        TrialStatus.PENDING: {TrialStatus.SCHEDULED, TrialStatus.SKIPPED, TrialStatus.ABORTED},
        TrialStatus.SCHEDULED: {TrialStatus.PREPARING, TrialStatus.SKIPPED, TrialStatus.ABORTED},
        TrialStatus.PREPARING: {
            TrialStatus.RUNNING,
            TrialStatus.FAILED,
            TrialStatus.RETRY_WAITING,
            TrialStatus.ABORTED,
        },
        TrialStatus.RUNNING: {
            TrialStatus.SCORING,
            TrialStatus.FAILED,
            TrialStatus.RETRY_WAITING,
            TrialStatus.ABORTED,
        },
        TrialStatus.SCORING: {TrialStatus.COMPLETED, TrialStatus.FAILED},
        TrialStatus.FAILED: {TrialStatus.RETRY_WAITING, TrialStatus.ABORTED},
        TrialStatus.RETRY_WAITING: {TrialStatus.SCHEDULED, TrialStatus.ABORTED},
        TrialStatus.COMPLETED: set(),
        TrialStatus.SKIPPED: set(),
        TrialStatus.ABORTED: set(),
    }

    def initialize(self, spec: TrialSpec, *, max_attempts: int) -> TrialState:
        return TrialState(
            spec=spec,
            status=spec.status,
            max_attempts=max_attempts,
        )

    def queue(self, state: TrialState, *, reason: str = "") -> TrialState:
        return self.transition(state, TrialStatus.SCHEDULED, event="queued", reason=reason)

    def start(self, state: TrialState, *, reason: str = "") -> TrialState:
        if state.status == TrialStatus.SCHEDULED:
            self.transition(state, TrialStatus.PREPARING, event="prepare", reason=reason)
        state.attempt_count += 1
        return self.transition(state, TrialStatus.RUNNING, event="start", reason=reason)

    def score(self, state: TrialState, *, reason: str = "") -> TrialState:
        return self.transition(state, TrialStatus.SCORING, event="score", reason=reason)

    def complete(self, state: TrialState, *, reason: str = "") -> TrialState:
        if state.status == TrialStatus.RUNNING:
            self.score(state, reason=reason)
        return self.transition(state, TrialStatus.COMPLETED, event="complete", reason=reason)

    def fail(
        self,
        state: TrialState,
        *,
        error_type: str,
        error_message: str,
        reason: str = "",
    ) -> TrialState:
        state.last_error_type = error_type
        state.last_error_message = error_message
        return self.transition(
            state,
            TrialStatus.FAILED,
            event="fail",
            reason=reason or error_message,
        )

    def mark_retry_waiting(self, state: TrialState, *, reason: str = "") -> TrialState:
        return self.transition(
            state,
            TrialStatus.RETRY_WAITING,
            event="retry_waiting",
            reason=reason,
        )

    def skip(self, state: TrialState, *, reason: str = "") -> TrialState:
        return self.transition(state, TrialStatus.SKIPPED, event="skip", reason=reason)

    def abort(self, state: TrialState, *, reason: str = "") -> TrialState:
        return self.transition(state, TrialStatus.ABORTED, event="abort", reason=reason)

    def transition(
        self,
        state: TrialState,
        new_status: TrialStatus,
        *,
        event: str,
        reason: str = "",
    ) -> TrialState:
        current_status = state.status
        if current_status == new_status:
            return state
        allowed = self._ALLOWED_TRANSITIONS[current_status]
        if new_status not in allowed:
            raise StateTransitionError(
                f"invalid transition {current_status.value} -> {new_status.value}"
            )
        state.history.append(
            TrialTransition(
                from_status=current_status.value,
                to_status=new_status.value,
                event=event,
                reason=reason,
            )
        )
        state.status = new_status
        return state
