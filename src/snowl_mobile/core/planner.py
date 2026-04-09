from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from snowl_mobile.artifacts.paths import slugify
from snowl_mobile.core.compatibility import CompatibilityResolver
from snowl_mobile.core.errors import RegistryError
from snowl_mobile.core.project_spec import ProjectSpec
from snowl_mobile.core.registry import Registry
from snowl_mobile.core.run_context import RunContext
from snowl_mobile.core.states import TrialStatus
from snowl_mobile.core.trial_spec import TrialSpec
from snowl_mobile.core.trial_state_machine import TrialState, TrialStateMachine
from snowl_mobile.schedulers.retry_controller import RetryController, TrialFailure
from snowl_mobile.schedulers.scheduler import Scheduler, SchedulerSnapshot


@dataclass(frozen=True, slots=True)
class TrialPlanDiagnostic:
    combination: str
    issues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BenchmarkTaskPlan:
    task_id: str
    instruction: str = ""
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TrialPlanEntry:
    trial: TrialSpec
    task: BenchmarkTaskPlan
    reports: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    run_context: RunContext
    planned_trials: tuple[TrialPlanEntry, ...]
    diagnostics: tuple[TrialPlanDiagnostic, ...]
    registry_summary: dict[str, list[str]]
    metadata_summary: dict[str, list[dict[str, object]]]

    @property
    def run_id(self) -> str:
        return self.run_context.run_id

    def to_summary(self) -> dict[str, Any]:
        return {
            "run": {
                "run_id": self.run_context.run_id,
                "status": self.run_context.status.value,
                "planned_trials": self.run_context.planned_trials,
                "diagnostics": self.run_context.diagnostics,
            },
            "registry": self.registry_summary,
            "registry_metadata": self.metadata_summary,
            "matrix": {
                "candidate_combinations": len(self.planned_trials) + len(self.diagnostics),
                "planned_trials": len(self.planned_trials),
                "incompatible_combinations": len(self.diagnostics),
            },
            "trials": [
                {
                    "trial_id": entry.trial.trial_id,
                    "agent_id": entry.trial.agent_id,
                    "agent_variant": entry.trial.agent_variant,
                    "benchmark_id": entry.trial.benchmark_id,
                    "task_id": entry.task.task_id,
                    "task_instruction": entry.task.instruction,
                    "model_id": entry.trial.model_id,
                    "seed": entry.trial.seed,
                    "status": entry.trial.status.value,
                    "artifact_level": entry.trial.artifact_level.value,
                    "worker_mode": entry.trial.runtime_recipe.worker_mode.value,
                    "integration_path": entry.trial.runtime_recipe.agent_runtime,
                    "bridge_id": entry.trial.runtime_recipe.bridge_id,
                    "pair_recipe_id": entry.trial.runtime_recipe.pair_recipe_id,
                    "ports": dict(entry.trial.runtime_recipe.ports),
                    "launch_hints": dict(entry.trial.runtime_recipe.launch_hints),
                    "reports": list(entry.reports),
                }
                for entry in self.planned_trials
            ],
            "diagnostics": [
                {"combination": diagnostic.combination, "issues": list(diagnostic.issues)}
                for diagnostic in self.diagnostics
            ],
        }


@dataclass(frozen=True, slots=True)
class SimulatedRunResult:
    run_context: RunContext
    plan: ExecutionPlan
    scheduler_snapshot: SchedulerSnapshot
    trial_states: tuple[TrialState, ...]

    def to_summary(self) -> dict[str, Any]:
        return {
            "run": {
                "run_id": self.run_context.run_id,
                "status": self.run_context.status.value,
                "planned_trials": self.run_context.planned_trials,
                "diagnostics": self.run_context.diagnostics,
            },
            "scheduler": self.scheduler_snapshot.to_dict(),
            "trials": [trial_state.to_summary() for trial_state in self.trial_states],
            "diagnostics": [
                {"combination": diagnostic.combination, "issues": list(diagnostic.issues)}
                for diagnostic in self.plan.diagnostics
            ],
        }


class ExecutionPlanner:
    def __init__(
        self,
        *,
        registry: Registry,
        compatibility_resolver: CompatibilityResolver | None = None,
        state_machine: TrialStateMachine | None = None,
    ) -> None:
        self.registry = registry
        self.compatibility_resolver = compatibility_resolver or CompatibilityResolver(registry=registry)
        self.state_machine = state_machine or TrialStateMachine()

    def plan(self, spec: ProjectSpec, *, run_id: str | None = None) -> ExecutionPlan:
        resolved_run_id = run_id or f"plan-{slugify(spec.project.run_name)}"
        run_context = RunContext(
            run_id=resolved_run_id,
            project_snapshot=spec,
            artifact_root=Path(spec.artifacts.root_dir) / resolved_run_id,
        )
        model_index = {model.model_id: model for model in spec.models}
        trials: list[TrialPlanEntry] = []
        diagnostics: list[TrialPlanDiagnostic] = []
        benchmark_tasks = {
            benchmark.benchmark_id: self._list_benchmark_tasks(benchmark.benchmark_id, run_context)
            for benchmark in spec.benchmarks
        }

        for seed in spec.matrix.seeds:
            for agent in spec.agents:
                for benchmark in spec.benchmarks:
                    for task in benchmark_tasks[benchmark.benchmark_id]:
                        combination = (
                            f"{agent.variant_id} x {benchmark.benchmark_id} x {task.task_id} x {seed}"
                        )
                        issues = self._check_registry_presence(agent.agent_id, benchmark.benchmark_id)
                        model = model_index[agent.model_ref]
                        recipe = spec.build_runtime_recipe(agent, benchmark)
                        reports = self.compatibility_resolver.aggregate(
                            agent=agent,
                            model=model,
                            benchmark=benchmark,
                            runtime_recipe=recipe,
                        )
                        issues.extend(self.compatibility_resolver.collect_issues(reports))

                        if issues:
                            diagnostics.append(
                                TrialPlanDiagnostic(combination=combination, issues=tuple(issues))
                            )
                            continue

                        trial = TrialSpec(
                            trial_id=self._build_trial_id(
                                spec.project.run_name,
                                agent.agent_id,
                                benchmark.benchmark_id,
                                seed,
                                task.task_id,
                            ),
                            run_id=resolved_run_id,
                            benchmark_id=benchmark.benchmark_id,
                            task_id=task.task_id,
                            agent_id=agent.agent_id,
                            agent_variant=agent.variant,
                            model_id=agent.model_ref,
                            seed=seed,
                            status=TrialStatus.PENDING,
                            artifact_level=spec.artifacts.level,
                            runtime_recipe=recipe,
                            timeout_sec=spec.runtime.timeout_sec,
                            max_steps=spec.runtime.max_steps,
                        )
                        trial.validate()
                        trials.append(
                            TrialPlanEntry(
                                trial=trial,
                                task=task,
                                reports=tuple(report.render() for report in reports),
                            )
                        )

        run_context.set_planned(planned_trials=len(trials), diagnostics=len(diagnostics))
        return ExecutionPlan(
            run_context=run_context,
            planned_trials=tuple(trials),
            diagnostics=tuple(diagnostics),
            registry_summary=self.registry.summary(),
            metadata_summary=self.registry.metadata_summary(),
        )

    def dry_run(
        self,
        spec: ProjectSpec,
        *,
        simulation_policy: Callable[[TrialState], TrialFailure | None] | None = None,
    ) -> SimulatedRunResult:
        plan = self.plan(spec)
        scheduler = Scheduler(state_machine=self.state_machine)
        retry_controller = RetryController(spec.retries)
        trial_states = [
            self.state_machine.initialize(
                entry.trial,
                max_attempts=retry_controller.max_attempts,
            )
            for entry in plan.planned_trials
        ]
        scheduler.submit_trials(trial_states)
        plan.run_context.sync_scheduler_counts(scheduler.snapshot().to_dict())

        simulate = simulation_policy or self._default_simulation_policy
        while True:
            trial_state = scheduler.poll_next_runnable_trial()
            if trial_state is None:
                break
            failure = simulate(trial_state)
            if failure is None:
                scheduler.mark_trial_finished(trial_state.trial_id, success=True)
            else:
                scheduler.mark_trial_finished(
                    trial_state.trial_id,
                    success=False,
                    retry_controller=retry_controller,
                    failure=failure,
                )
            plan.run_context.sync_scheduler_counts(scheduler.snapshot().to_dict())

        final_snapshot = scheduler.snapshot()
        plan.run_context.sync_scheduler_counts(final_snapshot.to_dict())
        return SimulatedRunResult(
            run_context=plan.run_context,
            plan=plan,
            scheduler_snapshot=final_snapshot,
            trial_states=tuple(scheduler.trial_states()),
        )

    def _default_simulation_policy(self, trial_state: TrialState) -> TrialFailure | None:
        if trial_state.spec.agent_id == "dummy_vision_agent" and trial_state.attempt_count == 1:
            return TrialFailure(
                error_type="MODEL_API_ERROR",
                message="simulated transient model failure",
            )
        return None

    def _check_registry_presence(self, agent_id: str, benchmark_id: str) -> list[str]:
        issues: list[str] = []
        try:
            self.registry.resolve_agent(agent_id)
        except RegistryError as error:
            issues.append(str(error))
        try:
            self.registry.resolve_benchmark(benchmark_id)
        except RegistryError as error:
            issues.append(str(error))
        return issues

    def _list_benchmark_tasks(
        self,
        benchmark_id: str,
        run_context: RunContext,
    ) -> tuple[BenchmarkTaskPlan, ...]:
        try:
            adapter = self.registry.instantiate_benchmark(benchmark_id)
        except RegistryError:
            return (BenchmarkTaskPlan(task_id=f"{benchmark_id}:planned-task"),)

        tasks = [
            self._normalize_task(raw_task, index=index, benchmark_id=benchmark_id)
            for index, raw_task in enumerate(adapter.list_tasks(run_context), start=1)
        ]
        if not tasks:
            return (BenchmarkTaskPlan(task_id=f"{benchmark_id}:planned-task"),)
        return tuple(tasks)

    def _normalize_task(
        self,
        raw_task: object,
        *,
        index: int,
        benchmark_id: str,
    ) -> BenchmarkTaskPlan:
        if isinstance(raw_task, dict):
            task_id = str(raw_task.get("task_id") or raw_task.get("id") or f"{benchmark_id}:task-{index:03d}")
            instruction = str(raw_task.get("instruction", ""))
            payload = {str(key): value for key, value in raw_task.items()}
            return BenchmarkTaskPlan(task_id=task_id, instruction=instruction, payload=payload)

        task_id = str(getattr(raw_task, "task_id", f"{benchmark_id}:task-{index:03d}"))
        instruction = str(getattr(raw_task, "instruction", ""))
        return BenchmarkTaskPlan(task_id=task_id, instruction=instruction)

    def _build_trial_id(
        self, run_name: str, agent_id: str, benchmark_id: str, seed: str, task_id: str
    ) -> str:
        run_slug = slugify(run_name)
        parts = [run_slug]
        for value in (agent_id, benchmark_id):
            value_slug = slugify(value)
            if value_slug and value_slug not in run_slug:
                parts.append(value_slug)
        parts.extend([slugify(task_id), slugify(seed)])
        return "-".join(parts)


ProjectPlanner = ExecutionPlanner
