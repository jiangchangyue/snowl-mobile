from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from snowl_mobile.core.project_spec import ProjectSpec
from snowl_mobile.core.states import RunStatus
from snowl_mobile.schemas.base import SchemaModel


@dataclass(slots=True)
class RunContext(SchemaModel):
    run_id: str
    project_snapshot: ProjectSpec
    artifact_root: Path
    status: RunStatus = RunStatus.CREATED
    planned_trials: int = 0
    diagnostics: int = 0
    queued: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    retrying: int = 0

    def set_planned(self, *, planned_trials: int, diagnostics: int) -> None:
        self.planned_trials = planned_trials
        self.diagnostics = diagnostics
        self.status = RunStatus.PLANNED

    def sync_scheduler_counts(self, counts: dict[str, int]) -> None:
        self.queued = counts.get("queued", 0)
        self.running = counts.get("running", 0)
        self.succeeded = counts.get("succeeded", 0)
        self.failed = counts.get("failed", 0)
        self.skipped = counts.get("skipped", 0)
        self.retrying = counts.get("retrying", 0)

        if self.running or self.queued or self.retrying:
            self.status = RunStatus.RUNNING
        elif self.failed and (self.succeeded or self.skipped):
            self.status = RunStatus.PARTIALLY_FAILED
        elif self.failed:
            self.status = RunStatus.PARTIALLY_FAILED
        else:
            self.status = RunStatus.COMPLETED
