from __future__ import annotations

from snowl_mobile.adapters.benchmarks.base import BaseBenchmarkAdapter
from snowl_mobile.core.benchmark_spec import BenchmarkSpec, MetricSchemaSpec, TaskSourceSpec
from snowl_mobile.core.enums import IntegrationMode, TaskSourceKind
from snowl_mobile.core.errors import PhaseStubError
from snowl_mobile.core.run_context import RunContext
from snowl_mobile.core.trial_context import TrialContext
from snowl_mobile.schemas.observation import ObservationBundle


class MockBenchmarkRepoAdapter(BaseBenchmarkAdapter):
    """TODO: fill this adapter after inspecting the real benchmark repo.

    Repo: `mock-benchmark-repo`
    Local path: `references/benchmarks/mock-benchmark-repo`
    Suggested integration mode: `wrap`
    Inspector summary: Mock Benchmark Repo This is a local-only mock benchmark repository used to demonstrate the snowl-mobile integration toolkit. Entrypoint
    """

    @property
    def adapter_id(self) -> str:
        return "mock_benchmark_repo"

    def describe(self) -> BenchmarkSpec:
        return BenchmarkSpec(
            benchmark_id=self.adapter_id,
            display_name="Mock Benchmark Repo",
            integration_mode=IntegrationMode.WRAP,
            task_source=TaskSourceSpec(
                kind=TaskSourceKind.REFERENCE_REPO,
                path="references/benchmarks/mock-benchmark-repo",
                selector="tasks/tasks.json",
                manifest="tasks/tasks.json",
            ),
            metric_schema=MetricSchemaSpec(
                primary_metric="task_success",
                native_metrics=("TODO_native_metric",),
            ),
            scorer_ref="scorer.py",
            reset_policy="reset_env.py",
            reset_requirements={"requires_task_seed": False},
            device_backend="adb_appium",
            required_env=('adbutils', 'lxml'),
            supported_agent_ids=(),
        )

    def list_tasks(self, project_ctx: RunContext) -> list[object]:
        # TODO: implement task discovery from `tasks/tasks.json`.
        return []

    def prepare_trial(self, ctx: TrialContext) -> None:
        # TODO: implement pre-task setup using `prepare_trial` / `reset_env.py`.
        raise PhaseStubError("Scaffold only: implement benchmark prepare_trial here.")

    def seed_environment(self, ctx: TrialContext) -> None:
        # TODO: separate benchmark-native seeding from platform reset. Current candidate: `reset_env.py`.
        raise PhaseStubError("Scaffold only: implement benchmark seed_environment here.")

    def get_initial_observation(self, ctx: TrialContext) -> ObservationBundle:
        # TODO: map the upstream `ui_tree` observation into ObservationBundle.
        raise PhaseStubError("Scaffold only: implement benchmark observation transform here.")

    def run_entry(self, ctx: TrialContext) -> object:
        # TODO: connect the main benchmark run path at `benchmark_runner.py`.
        raise PhaseStubError("Scaffold only: connect the benchmark run entry here.")

    def capture_native_score(self, ctx: TrialContext) -> object:
        # TODO: capture benchmark-native metrics from `scorer.py` before adding platform metrics.
        raise PhaseStubError("Scaffold only: implement native score capture here.")

    def cleanup_trial(self, ctx: TrialContext) -> None:
        # TODO: implement cleanup using `reset_env.py`.
        raise PhaseStubError("Scaffold only: implement benchmark cleanup here.")
