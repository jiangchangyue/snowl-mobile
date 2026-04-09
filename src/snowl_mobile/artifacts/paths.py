from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def slugify(value: str) -> str:
    lowered = value.strip().lower().replace(" ", "-")
    return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in lowered)


def build_run_id(run_name: str) -> str:
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{slugify(run_name)}"


@dataclass(frozen=True, slots=True)
class RunLayout:
    run_id: str
    run_dir: Path
    manifest_path: Path
    project_snapshot_path: Path
    plan_path: Path
    summary_path: Path
    events_path: Path
    run_log_path: Path
    trials_dir: Path

    def trial_layout(self, trial_id: str) -> "TrialLayout":
        trial_dir = self.trials_dir / trial_id
        return TrialLayout(
            trial_id=trial_id,
            trial_dir=trial_dir,
            meta_path=trial_dir / "meta.json",
            runtime_recipe_path=trial_dir / "runtime_recipe.json",
            score_path=trial_dir / "score.json",
            trajectory_path=trial_dir / "trajectory.json",
            log_path=trial_dir / "trial.log",
            steps_dir=trial_dir / "steps",
        )


@dataclass(frozen=True, slots=True)
class TrialLayout:
    trial_id: str
    trial_dir: Path
    meta_path: Path
    runtime_recipe_path: Path
    score_path: Path
    trajectory_path: Path
    log_path: Path
    steps_dir: Path

    def step_dir(self, step_index: int) -> Path:
        return self.steps_dir / f"{step_index:04d}"
