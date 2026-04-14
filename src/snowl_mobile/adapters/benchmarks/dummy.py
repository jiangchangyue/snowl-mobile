from __future__ import annotations

from snowl_mobile.adapters.benchmarks.base import BaseBenchmarkAdapter
from snowl_mobile.core.benchmark_spec import BenchmarkSpec, MetricSchemaSpec, TaskSourceSpec
from snowl_mobile.core.enums import IntegrationMode, TaskSourceKind
from snowl_mobile.core.errors import PhaseStubError
from snowl_mobile.core.run_context import RunContext
from snowl_mobile.core.trial_context import TrialContext
from snowl_mobile.schemas.observation import ObservationBundle


class DummyBenchmarkAdapter(BaseBenchmarkAdapter):
    @property
    def adapter_id(self) -> str:
        return "dummy_benchmark"

    def describe(self) -> BenchmarkSpec:
        return BenchmarkSpec(
            benchmark_id=self.adapter_id,
            display_name="Dummy Benchmark",
            integration_mode=IntegrationMode.WRAP,
            task_source=TaskSourceSpec(kind=TaskSourceKind.INLINE, selector="default"),
            metric_schema=MetricSchemaSpec(
                primary_metric="task_success",
                native_metrics=("task_success", "step_count"),
            ),
            scorer_ref="dummy.native",
            reset_policy="snapshot_then_seed",
            reset_requirements={"baseline_snapshot": "clean-base", "requires_task_seed": True},
            device_backend="adb_appium",
            required_env=(),
            supported_agent_ids=("dummy_text_agent", "dummy_vision_agent"),
        )

    def list_tasks(self, project_ctx: RunContext) -> list[object]:
        return [
            {
                "task_id": "dummy-task-001",
                "instruction": "Open the demo settings screen.",
                "category": "navigation",
            },
            {
                "task_id": "dummy-task-002",
                "instruction": "Exercise retry and reset bookkeeping.",
                "category": "resilience",
            },
        ]

    def prepare_trial(self, ctx: TrialContext) -> None:
        raise PhaseStubError("Dummy benchmark adapter is a dry-run-only stub.")

    def seed_environment(self, ctx: TrialContext) -> None:
        raise PhaseStubError("Dummy benchmark adapter is a dry-run-only stub.")

    def get_initial_observation(self, ctx: TrialContext) -> ObservationBundle:
        raise PhaseStubError("Dummy benchmark adapter is a dry-run-only stub.")
