from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from snowl_mobile.artifacts.event_bus import EventBus
from snowl_mobile.artifacts.paths import RunLayout, TrialLayout, build_run_id
from snowl_mobile.artifacts.trajectory import (
    TrajectoryArtifacts,
    TrajectoryStep,
    TrajectoryTimestamps,
)
from snowl_mobile.core.enums import ArtifactLevel
from snowl_mobile.core.errors import ArtifactError
from snowl_mobile.core.logging import get_trial_logger
from snowl_mobile.core.planner import ExecutionPlan, SimulatedRunResult
from snowl_mobile.core.project_spec import ProjectSpec
from snowl_mobile.core.states import RunStatus, TrialStatus
from snowl_mobile.core.trial_state_machine import TrialState
from snowl_mobile.runtime.trial_orchestrator import (
    DummyPipelineRunResult,
    PlatformPipelineRunResult,
    TrialExecutionSummary,
)
from snowl_mobile.scoring.score_bundle import ScoreBundle
from snowl_mobile.schemas.action import ActionRecord
from snowl_mobile.schemas.observation import ObservationBundle


LOGGER = logging.getLogger(__name__)


class ArtifactStore:
    """Owns repository-local run and trial artifact persistence."""

    def __init__(self, output_root: Path | None = None) -> None:
        self.output_root = output_root

    def initialize_run(
        self,
        *,
        spec: ProjectSpec,
        project_source: Path,
        run_id: str,
        plan_payload: dict[str, Any],
        summary_payload: dict[str, Any],
        manifest_payload: dict[str, Any] | None = None,
    ) -> RunLayout:
        artifact_root = self.output_root or Path(spec.artifacts.root_dir)
        return self.initialize_run_directory(
            spec=spec,
            project_source=project_source,
            run_dir=artifact_root / run_id,
            run_id=run_id,
            plan_payload=plan_payload,
            summary_payload=summary_payload,
            manifest_payload=manifest_payload,
        )

    def build_run_layout(self, *, run_dir: Path, run_id: str | None = None) -> RunLayout:
        resolved_run_id = run_id or run_dir.name
        return RunLayout(
            run_id=resolved_run_id,
            run_dir=run_dir,
            manifest_path=run_dir / "manifest.json",
            project_snapshot_path=run_dir / "project.snapshot.yml",
            plan_path=run_dir / "plan.json",
            summary_path=run_dir / "summary.json",
            events_path=run_dir / "events.jsonl",
            run_log_path=run_dir / "run.log",
            trials_dir=run_dir / "trials",
        )

    def initialize_run_directory(
        self,
        *,
        spec: ProjectSpec,
        project_source: Path,
        run_dir: Path,
        run_id: str | None,
        plan_payload: dict[str, Any],
        summary_payload: dict[str, Any],
        manifest_payload: dict[str, Any] | None = None,
    ) -> RunLayout:
        layout = self.build_run_layout(run_dir=run_dir, run_id=run_id)
        try:
            layout.trials_dir.mkdir(parents=True, exist_ok=False)
        except OSError as error:
            raise ArtifactError(f"failed to create run directory: {layout.run_dir}") from error

        self._copy_project_snapshot(project_source, layout.project_snapshot_path)
        self.write_manifest(
            layout,
            manifest_payload
            or self._default_manifest_payload(spec=spec, layout=layout, summary_payload=summary_payload),
        )
        self.write_plan(layout, plan_payload)
        self.write_summary(layout, summary_payload)
        self.append_event(
            layout,
            {
                "event": "run_initialized",
                "run_id": run_id,
                "timestamp": self._utcnow(),
                "artifact_level": spec.artifacts.level.value,
                "project_snapshot": str(layout.project_snapshot_path.relative_to(layout.run_dir)),
            },
        )
        return layout

    def clear_trial_directory(self, layout: RunLayout, trial_id: str) -> None:
        trial_dir = layout.trial_layout(trial_id).trial_dir
        if not trial_dir.exists():
            return
        try:
            shutil.rmtree(trial_dir)
        except OSError as error:
            raise ArtifactError(f"failed to clear partial trial directory: {trial_dir}") from error

    def create_run_scaffold(self, spec: ProjectSpec, project_source: Path) -> RunLayout:
        run_id = build_run_id(spec.project.run_name)
        return self.initialize_run(
            spec=spec,
            project_source=project_source,
            run_id=run_id,
            plan_payload={
                "matrix_mode": spec.matrix.expand,
                "trial_groups": spec.expand_matrix(),
                "notes": [
                    "Schema and contract scaffold only. No scheduling or concrete TrialSpec execution yet."
                ],
            },
            summary_payload={
                "run_id": run_id,
                "status": RunStatus.CREATED.value,
                "counts": {
                    "planned_trials": spec.matrix_cardinality,
                    "completed": 0,
                    "failed": 0,
                    "retrying": 0,
                    "skipped": 0,
                },
                "notes": [
                    "Contract scaffold initialized. Runtime orchestration remains a later-phase stub."
                ],
            },
            manifest_payload={
                "layout_version": "snowl-mobile.p4",
                "run_id": run_id,
                "project_name": spec.project.name,
                "run_name": spec.project.run_name,
                "status": RunStatus.CREATED.value,
                "created_at": self._utcnow(),
                "artifact_level": spec.artifacts.level.value,
                "files": self._manifest_files(layout_run_id=run_id),
                "counts": {
                    "models": len(spec.models),
                    "agents": len(spec.agents),
                    "benchmarks": len(spec.benchmarks),
                    "planned_trial_groups": spec.matrix_cardinality,
                },
            },
        )

    def build_summary_payload(self, result: SimulatedRunResult) -> dict[str, Any]:
        return self._build_summary_payload(result)

    def build_pipeline_summary_payload(self, result: DummyPipelineRunResult) -> dict[str, Any]:
        return self._build_pipeline_summary_payload(result)

    def build_platform_pipeline_summary_payload(
        self, result: PlatformPipelineRunResult
    ) -> dict[str, Any]:
        return self._build_platform_pipeline_summary_payload(result)

    def build_manifest_payload(
        self,
        *,
        spec: ProjectSpec,
        layout: RunLayout,
        summary_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._default_manifest_payload(
            spec=spec,
            layout=layout,
            summary_payload=summary_payload,
        )

    def persist_simulated_run(
        self,
        *,
        layout: RunLayout,
        spec: ProjectSpec,
        plan: ExecutionPlan,
        result: SimulatedRunResult,
    ) -> None:
        LOGGER.info("Persisting simulated run artifacts under %s", layout.run_dir)
        self.write_plan(layout, plan.to_summary())
        summary_payload = self._build_summary_payload(result)
        self.write_summary(layout, summary_payload)
        self.write_manifest(
            layout,
            self._default_manifest_payload(
                spec=spec,
                layout=layout,
                summary_payload=summary_payload,
            ),
        )
        self.append_event(
            layout,
            {
                "event": "plan_persisted",
                "run_id": layout.run_id,
                "timestamp": self._utcnow(),
                "planned_trials": len(plan.planned_trials),
                "diagnostics": len(plan.diagnostics),
            },
        )

        for trial_state in result.trial_states:
            trial_layout = self.initialize_trial(layout, trial_state)
            trial_logger = (
                get_trial_logger(trial_state.trial_id, trial_layout.log_path)
                if spec.artifacts.persist_logs
                else get_trial_logger(trial_state.trial_id)
            )
            trial_logger.info(
                "Persisting simulated trial '%s' with status %s",
                trial_state.trial_id,
                trial_state.status.value,
            )
            self.write_trial_meta(trial_layout, trial_state)
            self.write_trial_runtime_recipe(trial_layout, trial_state)
            score_bundle = self._build_score_bundle(trial_state)
            self.write_trial_score(trial_layout, score_bundle)
            steps = self._build_trajectory_steps(
                trial_layout=trial_layout,
                trial_state=trial_state,
                level=spec.artifacts.level,
                persist_step_artifacts=spec.artifacts.persist_step_artifacts,
            )
            self.write_trial_trajectory(trial_layout, steps)
            self._emit_trial_events(layout=layout, trial_state=trial_state, steps=steps)
            trial_logger.info(
                "Persisted trial '%s': %s attempt(s), %s trajectory step(s)",
                trial_state.trial_id,
                trial_state.attempt_count,
                len(steps),
            )

        self.append_event(
            layout,
            {
                "event": "run_completed",
                "run_id": layout.run_id,
                "timestamp": self._utcnow(),
                "status": result.run_context.status.value,
                "summary_path": str(layout.summary_path.relative_to(layout.run_dir)),
            },
        )
        LOGGER.info("Completed simulated artifact export for run '%s'", layout.run_id)

    def persist_pipeline_run(
        self,
        *,
        layout: RunLayout,
        spec: ProjectSpec,
        plan: ExecutionPlan,
        result: DummyPipelineRunResult,
    ) -> None:
        LOGGER.info("Persisting executed dummy pipeline artifacts under %s", layout.run_dir)
        self.write_plan(layout, plan.to_summary())
        summary_payload = self._build_pipeline_summary_payload(result)
        self.write_summary(layout, summary_payload)
        self.write_manifest(
            layout,
            self._default_manifest_payload(
                spec=spec,
                layout=layout,
                summary_payload=summary_payload,
            ),
        )
        self.append_event(
            layout,
            {
                "event": "run_started",
                "run_id": layout.run_id,
                "timestamp": result.started_at,
                "planned_trials": len(plan.planned_trials),
            },
        )
        summary_by_trial = {summary.trial_id: summary for summary in result.trial_summaries}

        for trial_state in result.trial_states:
            trial_summary = summary_by_trial[trial_state.trial_id]
            trial_layout = self.initialize_trial(layout, trial_state)
            trial_logger = (
                get_trial_logger(trial_state.trial_id, trial_layout.log_path)
                if spec.artifacts.persist_logs
                else get_trial_logger(trial_state.trial_id)
            )
            trial_logger.info(
                "Persisting executed trial '%s' with status %s",
                trial_state.trial_id,
                trial_state.status.value,
            )
            self.write_trial_meta(
                trial_layout,
                trial_state,
                extra={
                    "task_id": trial_summary.task_id,
                    "platform_metrics": trial_summary.platform_metrics,
                    "execution_modes": list(trial_summary.execution_modes),
                    "instance_ids": list(trial_summary.instance_ids),
                },
            )
            self.write_trial_runtime_recipe(trial_layout, trial_state)
            score_bundle = self._build_score_bundle(
                trial_state,
                duration_ms=trial_summary.total_duration_ms,
                extra_platform_metrics=trial_summary.platform_metrics,
            )
            self.write_trial_score(trial_layout, score_bundle)
            steps = self._build_trajectory_steps(
                trial_layout=trial_layout,
                trial_state=trial_state,
                level=spec.artifacts.level,
                persist_step_artifacts=spec.artifacts.persist_step_artifacts,
            )
            self.write_trial_trajectory(trial_layout, steps)
            self._emit_trial_events(layout=layout, trial_state=trial_state, steps=steps)
            self.append_event(
                layout,
                {
                    "event": "trial_finished",
                    "run_id": layout.run_id,
                    "trial_id": trial_state.trial_id,
                    "timestamp": self._utcnow(),
                    "duration_ms": trial_summary.total_duration_ms,
                    "worker_attempts": trial_summary.worker_attempts,
                    "instance_ids": list(trial_summary.instance_ids),
                },
            )
            trial_logger.info(
                "Persisted executed trial '%s': duration_ms=%s worker_attempts=%s",
                trial_state.trial_id,
                trial_summary.total_duration_ms,
                trial_summary.worker_attempts,
            )

        self.append_event(
            layout,
            {
                "event": "run_completed",
                "run_id": layout.run_id,
                "timestamp": result.finished_at,
                "status": result.plan.run_context.status.value,
                "total_duration_ms": result.total_duration_ms,
            },
        )
        LOGGER.info("Completed dummy pipeline artifact export for run '%s'", layout.run_id)

    def persist_platform_pipeline_run(
        self,
        *,
        layout: RunLayout,
        spec: ProjectSpec,
        plan: ExecutionPlan,
        result: PlatformPipelineRunResult,
    ) -> None:
        LOGGER.info("Persisting platform pipeline artifacts under %s", layout.run_dir)
        self.write_plan(layout, plan.to_summary())
        summary_payload = self._build_platform_pipeline_summary_payload(result)
        self.write_summary(layout, summary_payload)
        self.write_manifest(
            layout,
            self._default_manifest_payload(
                spec=spec,
                layout=layout,
                summary_payload=summary_payload,
            ),
        )
        self.append_event(
            layout,
            {
                "event": "run_started",
                "run_id": layout.run_id,
                "timestamp": result.started_at,
                "planned_trials": len(plan.planned_trials),
            },
        )
        summary_by_trial = {summary.trial_id: summary for summary in result.trial_summaries}
        artifact_by_trial = {artifact.trial_id: artifact for artifact in result.trial_artifacts}

        for trial_state in result.trial_states:
            trial_summary = summary_by_trial[trial_state.trial_id]
            trial_artifact = artifact_by_trial.get(trial_state.trial_id)
            trial_layout = self.initialize_trial(layout, trial_state, exist_ok=True)
            trial_logger = (
                get_trial_logger(trial_state.trial_id, trial_layout.log_path)
                if spec.artifacts.persist_logs
                else get_trial_logger(trial_state.trial_id)
            )
            trial_logger.info(
                "Persisting platform trial '%s' with status %s",
                trial_state.trial_id,
                trial_state.status.value,
            )
            extra = {
                "task_id": trial_summary.task_id,
                "platform_metrics": trial_summary.platform_metrics,
                "execution_modes": list(trial_summary.execution_modes),
                "instance_ids": list(trial_summary.instance_ids),
            }
            if trial_artifact is not None:
                extra["raw_artifacts"] = dict(trial_artifact.raw_artifacts)
                extra["notes"] = list(trial_artifact.notes)
            steps = self.persist_platform_trial_artifacts(
                layout=layout,
                spec=spec,
                trial_state=trial_state,
                trial_summary=trial_summary,
                trial_artifact=trial_artifact,
            )
            self._emit_trial_events(layout=layout, trial_state=trial_state, steps=steps)
            self.append_event(
                layout,
                {
                    "event": "trial_finished",
                    "run_id": layout.run_id,
                    "trial_id": trial_state.trial_id,
                    "timestamp": self._utcnow(),
                    "duration_ms": trial_summary.total_duration_ms,
                    "worker_attempts": trial_summary.worker_attempts,
                    "instance_ids": list(trial_summary.instance_ids),
                    "primary_metric": trial_summary.primary_metric,
                },
            )
            trial_logger.info(
                "Persisted platform trial '%s': duration_ms=%s primary_metric=%s",
                trial_state.trial_id,
                trial_summary.total_duration_ms,
                trial_summary.primary_metric,
            )

        self.append_event(
            layout,
            {
                "event": "run_completed",
                "run_id": layout.run_id,
                "timestamp": result.finished_at,
                "status": result.plan.run_context.status.value,
                "total_duration_ms": result.total_duration_ms,
            },
        )
        LOGGER.info("Completed platform pipeline artifact export for run '%s'", layout.run_id)

    def persist_platform_trial_artifacts(
        self,
        *,
        layout: RunLayout,
        spec: ProjectSpec,
        trial_state: TrialState,
        trial_summary: TrialExecutionSummary,
        trial_artifact: TrialArtifactRecord | None,
    ) -> list[TrajectoryStep]:
        trial_layout = self.initialize_trial(layout, trial_state, exist_ok=True)
        extra = {
            "task_id": trial_summary.task_id,
            "platform_metrics": trial_summary.platform_metrics,
            "execution_modes": list(trial_summary.execution_modes),
            "instance_ids": list(trial_summary.instance_ids),
        }
        if trial_artifact is not None:
            extra["raw_artifacts"] = dict(trial_artifact.raw_artifacts)
            extra["notes"] = list(trial_artifact.notes)
        self.write_trial_meta(trial_layout, trial_state, extra=extra)
        self.write_trial_runtime_recipe(trial_layout, trial_state)
        if trial_artifact is not None:
            self.write_trial_score(trial_layout, trial_artifact.score_bundle)
            steps = list(trial_artifact.trajectory_steps)
            self.write_trial_trajectory(trial_layout, steps)
            return steps

        score_bundle = self._build_score_bundle(
            trial_state,
            duration_ms=trial_summary.total_duration_ms,
            extra_platform_metrics=trial_summary.platform_metrics,
        )
        self.write_trial_score(trial_layout, score_bundle)
        if self._has_failure_diagnostics(trial_layout):
            self.write_trial_trajectory(trial_layout, [])
            return []
        steps = self._build_trajectory_steps(
            trial_layout=trial_layout,
            trial_state=trial_state,
            level=spec.artifacts.level,
            persist_step_artifacts=spec.artifacts.persist_step_artifacts,
        )
        self.write_trial_trajectory(trial_layout, steps)
        return steps

    def write_manifest(self, layout: RunLayout, payload: dict[str, Any]) -> None:
        self._write_json(layout.manifest_path, payload)

    def write_plan(self, layout: RunLayout, payload: dict[str, Any]) -> None:
        self._write_json(layout.plan_path, payload)

    def write_project_snapshot(self, layout: RunLayout, source: Path) -> None:
        self._copy_project_snapshot(source, layout.project_snapshot_path)

    def write_summary(self, layout: RunLayout, payload: dict[str, Any]) -> None:
        self._write_json(layout.summary_path, payload)

    def write_eval_results(self, layout: RunLayout, payload: dict[str, Any]) -> None:
        self._write_json(layout.run_dir / "eval_results.json", payload)

    def append_event(self, layout: RunLayout, event: dict[str, Any]) -> None:
        EventBus(layout.events_path).write_event(event)

    def initialize_trial(
        self,
        layout: RunLayout,
        trial_state: TrialState,
        *,
        exist_ok: bool = False,
    ) -> TrialLayout:
        trial_layout = layout.trial_layout(trial_state.trial_id)
        try:
            trial_layout.steps_dir.mkdir(parents=True, exist_ok=exist_ok)
            trial_layout.log_path.touch(exist_ok=True)
        except OSError as error:
            raise ArtifactError(f"failed to create trial directory: {trial_layout.trial_dir}") from error
        return trial_layout

    def write_trial_meta(
        self,
        trial_layout: TrialLayout,
        trial_state: TrialState,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "trial_id": trial_state.trial_id,
            "run_id": trial_state.spec.run_id,
            "status": trial_state.status.value,
            "artifact_level": trial_state.spec.artifact_level.value,
            "attempt_count": trial_state.attempt_count,
            "max_attempts": trial_state.max_attempts,
            "last_error_type": trial_state.last_error_type,
            "last_error_message": trial_state.last_error_message,
            "spec": self._to_jsonable(trial_state.spec),
            "history": [transition.to_dict() for transition in trial_state.history],
        }
        if extra:
            payload.update(extra)
        self._write_json(trial_layout.meta_path, payload)

    def write_trial_score(self, trial_layout: TrialLayout, score_bundle: ScoreBundle) -> None:
        self._write_json(trial_layout.score_path, self._to_jsonable(score_bundle))

    def write_trial_runtime_recipe(self, trial_layout: TrialLayout, trial_state: TrialState) -> None:
        self._write_json(
            trial_layout.runtime_recipe_path,
            self._to_jsonable(trial_state.spec.runtime_recipe),
        )

    def write_trial_trajectory(
        self,
        trial_layout: TrialLayout,
        steps: list[TrajectoryStep],
    ) -> None:
        try:
            payload = {
                "trial_id": trial_layout.trial_id,
                "task_instruction": next(
                    (step.task_instruction for step in steps if step.task_instruction),
                    None,
                ),
                "step_count": len(steps),
                "score_path": trial_layout.score_path.name,
                "steps": [self._to_user_trajectory_step(step) for step in steps],
            }
            self._write_json(trial_layout.trajectory_path, payload)
        except OSError as error:
            raise ArtifactError(
                f"failed to write trajectory json: {trial_layout.trajectory_path}"
            ) from error

    def _has_failure_diagnostics(self, trial_layout: TrialLayout) -> bool:
        raw_dir = trial_layout.trial_dir / "raw"
        if not raw_dir.exists():
            return False
        return any(raw_dir.rglob("failure.json"))

    def _to_user_trajectory_step(self, step: TrajectoryStep) -> dict[str, Any]:
        observation_extra = dict(step.observation.extra)
        parsed_action = dict(step.action.parsed_action)
        action_payload = (
            dict(parsed_action.get("arguments"))
            if isinstance(parsed_action.get("arguments"), dict)
            else parsed_action
        )
        action_input = {
            key: value
            for key, value in action_payload.items()
            if key not in {"_metadata", "action", "name"}
        }
        key_ui_elements = [
            item.get("label")
            for item in observation_extra.get("ui_summary", [])
            if isinstance(item, dict) and item.get("label")
        ][:10]
        return {
            "step": step.step_index,
            "thought": step.thought or "",
            "action": (
                step.action.executed_action.get("action_name")
                or step.action.executed_action.get("normalized_action")
                or ""
            ),
            "action_input": self._to_jsonable(action_input),
            "raw_action": step.action_text or "",
            "observation": {
                "package_name": step.observation.package_name,
                "activity": step.observation.activity,
                "screen_size": step.observation.screen_size,
                "visible_text": step.observation.parsed_text,
                "key_ui_elements": key_ui_elements,
            },
            "artifacts": {
                "screenshot_path": step.artifacts.screenshot_path,
                "xml_path": step.artifacts.xml_path,
                "model_response_text_path": step.artifacts.model_response_text_path,
                "model_response_json_path": step.artifacts.model_response_json_path,
            },
        }

    def _build_summary_payload(self, result: SimulatedRunResult) -> dict[str, Any]:
        return {
            "run_id": result.run_context.run_id,
            "status": result.run_context.status.value,
            "counts": {
                "planned_trials": result.run_context.planned_trials,
                "diagnostics": result.run_context.diagnostics,
                "queued": result.run_context.queued,
                "running": result.run_context.running,
                "completed": result.run_context.succeeded,
                "failed": result.run_context.failed,
                "retrying": result.run_context.retrying,
                "skipped": result.run_context.skipped,
            },
            "exact_status_counts": result.scheduler_snapshot.exact_status_counts,
            "trials": [
                {
                    "trial_id": trial_state.trial_id,
                    "status": trial_state.status.value,
                    "attempt_count": trial_state.attempt_count,
                }
                for trial_state in result.trial_states
            ],
            "notes": [
                "Simulated dry-run artifacts only. No real benchmark execution or emulator control occurred."
            ],
        }

    def _build_pipeline_summary_payload(self, result: DummyPipelineRunResult) -> dict[str, Any]:
        summary = result.to_summary()
        return {
            "run_id": result.plan.run_id,
            "status": result.plan.run_context.status.value,
            "counts": summary["counts"],
            "metrics_summary": summary["metrics_summary"],
            "scheduler": summary["scheduler"],
            "pool": summary["pool"],
            "trials": [trial for trial in summary["trials"]],
            "notes": [
                "Executed dummy pipeline only. Dummy adapters were used, while emulator handling depended on the selected device_mode."
            ],
        }

    def _build_platform_pipeline_summary_payload(
        self, result: PlatformPipelineRunResult
    ) -> dict[str, Any]:
        summary = result.to_summary()
        return {
            "run_id": result.plan.run_id,
            "status": result.plan.run_context.status.value,
            "counts": summary["counts"],
            "metrics_summary": summary["metrics_summary"],
            "scheduler": summary["scheduler"],
            "pool": summary["pool"],
            "trials": [trial for trial in summary["trials"]],
            "notes": list(summary.get("notes", [])) or [
                "Executed platform pipeline with pair-aware bridge resolution."
            ],
        }

    def _default_manifest_payload(
        self,
        *,
        spec: ProjectSpec,
        layout: RunLayout,
        summary_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "layout_version": "snowl-mobile.p4",
            "run_id": layout.run_id,
            "project_name": spec.project.name,
            "run_name": spec.project.run_name,
            "status": summary_payload.get("status", RunStatus.CREATED.value),
            "created_at": self._utcnow(),
            "artifact_level": spec.artifacts.level.value,
            "files": {
                "manifest": layout.manifest_path.name,
                "plan": layout.plan_path.name,
                "summary": layout.summary_path.name,
                "events": layout.events_path.name,
                "run_log": layout.run_log_path.name,
                "trials_dir": layout.trials_dir.name,
                "project_snapshot": layout.project_snapshot_path.name,
            },
            "counts": {
                "models": len(spec.models),
                "agents": len(spec.agents),
                "benchmarks": len(spec.benchmarks),
                "planned_trial_groups": summary_payload.get("counts", {}).get("planned_trials", 0),
            },
        }

    def _manifest_files(self, *, layout_run_id: str) -> dict[str, str]:
        return {
            "manifest": "manifest.json",
            "plan": "plan.json",
            "summary": "summary.json",
            "events": "events.jsonl",
            "run_log": "run.log",
            "trials_dir": "trials",
            "project_snapshot": "project.snapshot.yml",
            "run_id": layout_run_id,
        }

    def _build_score_bundle(
        self,
        trial_state: TrialState,
        *,
        duration_ms: int | None = None,
        extra_platform_metrics: dict[str, Any] | None = None,
    ) -> ScoreBundle:
        succeeded = trial_state.status == TrialStatus.COMPLETED
        platform_metrics = {
            "final_status": trial_state.status.value,
            "retry_count": max(trial_state.attempt_count - 1, 0),
        }
        if duration_ms is not None:
            platform_metrics["duration_ms"] = duration_ms
        if extra_platform_metrics:
            platform_metrics.update(extra_platform_metrics)
        return ScoreBundle(
            native_metrics={
                "task_success": 1 if succeeded else 0,
                "attempt_count": trial_state.attempt_count,
            },
            primary_metric=1 if succeeded else 0,
            platform_metrics=platform_metrics,
            notes=[
                "Simulated score bundle. Native scorer integration is still out of scope for this phase."
            ],
        )

    def _build_trajectory_steps(
        self,
        *,
        trial_layout: TrialLayout,
        trial_state: TrialState,
        level: ArtifactLevel,
        persist_step_artifacts: bool,
    ) -> list[TrajectoryStep]:
        base_time = datetime.now(tz=timezone.utc)
        steps: list[TrajectoryStep] = []
        for step_index in range(1, trial_state.attempt_count + 1):
            step_dir = trial_layout.step_dir(step_index)
            observation_path: str | None = None
            action_path: str | None = None
            screenshot_path: str | None = None
            xml_path: str | None = None

            if level != ArtifactLevel.LIGHT and persist_step_artifacts:
                try:
                    step_dir.mkdir(parents=True, exist_ok=True)
                except OSError as error:
                    raise ArtifactError(f"failed to create step directory: {step_dir}") from error
                observation_path = str((step_dir / "observation.json").relative_to(trial_layout.trial_dir))
                action_path = str((step_dir / "action.json").relative_to(trial_layout.trial_dir))
                screenshot_path = str((step_dir / "screenshot.txt").relative_to(trial_layout.trial_dir))
                xml_path = str((step_dir / "hierarchy.xml").relative_to(trial_layout.trial_dir))

            failed_attempt = (
                step_index < trial_state.attempt_count
                or trial_state.status in {TrialStatus.FAILED, TrialStatus.ABORTED}
            )
            step_status = "failed" if failed_attempt else "completed"
            observed_at = base_time + timedelta(seconds=(step_index - 1) * 3)
            action_at = observed_at + timedelta(seconds=1)
            persisted_at = observed_at + timedelta(seconds=2)

            observation = ObservationBundle(
                timestamp=observed_at.isoformat(),
                screenshot_path=screenshot_path,
                xml_path=xml_path,
                parsed_text=f"stub observation for {trial_state.trial_id} attempt {step_index}",
                activity="DummyActivity",
                package_name="com.snowl.mobile.dummy",
                screen_size="1080x2400",
                orientation="portrait",
                source_backend=trial_state.spec.runtime_recipe.control_backend,
                extra={
                    "attempt": step_index,
                    "simulated": True,
                    "trial_status": trial_state.status.value,
                },
            )
            action = ActionRecord(
                agent_raw_output=f"tap(action_button_{step_index})",
                parsed_action={"type": "tap", "target": f"action_button_{step_index}"},
                executed_action={"backend": "stub", "command": f"tap:{step_index}"},
                execution_result={
                    "status": step_status,
                    "error_type": trial_state.last_error_type if failed_attempt else None,
                },
            )
            if observation_path is not None and action_path is not None:
                self._write_json(step_dir / "observation.json", self._to_jsonable(observation))
                self._write_json(step_dir / "action.json", self._to_jsonable(action))
                self._write_text(
                    step_dir / "screenshot.txt",
                    f"stub screenshot placeholder for {trial_state.trial_id} step {step_index}\n",
                )
                self._write_text(
                    step_dir / "hierarchy.xml",
                    (
                        "<hierarchy>"
                        f"<node trial=\"{trial_state.trial_id}\" step=\"{step_index}\" />"
                        "</hierarchy>\n"
                    ),
                )
                if level == ArtifactLevel.FULL:
                    self._write_json(
                        step_dir / "prompt_payload.json",
                        {
                            "trial_id": trial_state.trial_id,
                            "step_index": step_index,
                            "payload_kind": "stub_prompt_payload",
                            "notes": ["full artifact level placeholder"],
                        },
                    )

            steps.append(
                TrajectoryStep(
                    step_index=step_index,
                    attempt=step_index,
                    status=step_status,
                    observation=observation,
                    action=action,
                    artifacts=TrajectoryArtifacts(
                        observation_path=observation_path,
                        action_path=action_path,
                        screenshot_path=screenshot_path,
                        xml_path=xml_path,
                    ),
                    timestamps=TrajectoryTimestamps(
                        observed_at=observed_at.isoformat(),
                        action_at=action_at.isoformat(),
                        persisted_at=persisted_at.isoformat(),
                    ),
                    notes=[
                        "Simulated trajectory step. No real screenshot or XML capture occurred."
                    ],
                )
            )
        return steps

    def _emit_trial_events(
        self,
        *,
        layout: RunLayout,
        trial_state: TrialState,
        steps: list[TrajectoryStep],
    ) -> None:
        self.append_event(
            layout,
            {
                "event": "trial_persisted",
                "run_id": layout.run_id,
                "trial_id": trial_state.trial_id,
                "timestamp": self._utcnow(),
                "status": trial_state.status.value,
                "attempt_count": trial_state.attempt_count,
                "trajectory_steps": len(steps),
            },
        )
        for index, transition in enumerate(trial_state.history, start=1):
            self.append_event(
                layout,
                {
                    "event": "trial_status_transition",
                    "run_id": layout.run_id,
                    "trial_id": trial_state.trial_id,
                    "timestamp": self._utcnow(),
                    "sequence": index,
                    "from_status": transition.from_status,
                    "to_status": transition.to_status,
                    "reason": transition.reason,
                },
            )

    def _copy_project_snapshot(self, source: Path, destination: Path) -> None:
        try:
            destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError as error:
            raise ArtifactError(
                f"failed to persist project snapshot from {source} to {destination}"
            ) from error

    def _write_json(self, path: Path, payload: dict[str, Any] | list[Any]) -> None:
        try:
            path.write_text(
                json.dumps(self._to_jsonable(payload), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as error:
            raise ArtifactError(f"failed to write artifact file: {path}") from error

    def _write_text(self, path: Path, payload: str) -> None:
        try:
            path.write_text(payload, encoding="utf-8")
        except OSError as error:
            raise ArtifactError(f"failed to write artifact file: {path}") from error

    def _to_jsonable(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._to_jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._to_jsonable(item) for item in value]
        if isinstance(value, Path):
            return str(value)
        if hasattr(value, "value"):
            return value.value
        if hasattr(value, "__dataclass_fields__"):
            return self._to_jsonable(asdict(value))
        return value

    def _utcnow(self) -> str:
        return datetime.now(tz=timezone.utc).isoformat()
