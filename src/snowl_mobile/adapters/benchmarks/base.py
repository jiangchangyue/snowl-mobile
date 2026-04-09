from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from snowl_mobile.adapters.base import AdapterMetadata, BaseAdapter
from snowl_mobile.core.benchmark_spec import BenchmarkSpec
from snowl_mobile.core.errors import PhaseStubError
from snowl_mobile.core.run_context import RunContext
from snowl_mobile.core.trial_context import TrialContext
from snowl_mobile.scoring.score_bundle import ScoreBundle
from snowl_mobile.schemas.observation import ObservationBundle


@dataclass(frozen=True, slots=True)
class BenchmarkProbeRequest:
    trial_context: TrialContext
    output_dir: Path
    operation: str
    task_payload: dict[str, object] = field(default_factory=dict)
    task_instruction: str = ""
    emulator_instance: object | None = None
    mock_mode: bool = False


@dataclass(frozen=True, slots=True)
class BenchmarkProbeResult:
    observation: ObservationBundle
    score_bundle: ScoreBundle
    raw_artifacts: dict[str, str] = field(default_factory=dict)
    notes: tuple[str, ...] = ()


class BaseBenchmarkAdapter(BaseAdapter, ABC):
    """Recommended benchmark structure:

    1. `list_tasks()` resolves benchmark-native task discovery.
    2. `prepare_trial()` handles pre-task setup owned by the benchmark.
    3. `seed_environment()` handles benchmark-native reset/seed logic, separate from platform reset.
    4. `get_initial_observation()` maps upstream observations into `ObservationBundle`.
    5. native scorer output should remain in benchmark-native metrics; platform metrics are added later by the host.
    6. cleanup and raw artifact capture should stay explicit so future integrations remain auditable.
    """

    kind = "benchmark"

    @abstractmethod
    def describe(self) -> BenchmarkSpec:
        """Return the canonical BenchmarkSpec exposed by this adapter."""

    @abstractmethod
    def list_tasks(self, project_ctx: RunContext) -> list[object]:
        """Return benchmark task descriptors."""

    @abstractmethod
    def prepare_trial(self, ctx: TrialContext) -> None:
        """Prepare benchmark state before a trial starts."""

    @abstractmethod
    def seed_environment(self, ctx: TrialContext) -> None:
        """Inject benchmark-specific state into the environment."""

    @abstractmethod
    def get_initial_observation(self, ctx: TrialContext) -> ObservationBundle:
        """Return the first observation for the trial."""

    def cleanup_trial(self, ctx: TrialContext) -> None:
        """Optional cleanup hook for benchmark-native teardown."""

    def capture_raw_artifacts(self, ctx: TrialContext) -> dict[str, str]:
        """Optional hook returning raw artifact refs produced by the benchmark."""
        return {}

    def map_native_metrics(self, native_metrics: dict[str, object]) -> dict[str, object]:
        """Optional hook for explicit native-metric to platform-metric mapping."""
        return native_metrics

    def build_probe_request(
        self,
        ctx: TrialContext,
        *,
        output_dir: Path,
        operation: str,
        task_payload: dict[str, object],
        task_instruction: str,
        emulator_instance: object | None,
        mock_mode: bool,
    ) -> BenchmarkProbeRequest:
        raise PhaseStubError(
            "This benchmark adapter does not expose a benchmark-side probe path in the current phase."
        )

    def run_benchmark_probe(self, request: BenchmarkProbeRequest) -> BenchmarkProbeResult:
        raise PhaseStubError(
            "This benchmark adapter does not expose a benchmark-side probe path in the current phase."
        )

    def metadata(self) -> AdapterMetadata:
        spec = self.describe()
        return AdapterMetadata(
            adapter_id=spec.benchmark_id,
            kind=self.kind,
            integration_mode=spec.integration_mode.value,
            supported_backends=(spec.device_backend,),
            required_env=spec.required_env,
            supported_benchmarks=(spec.benchmark_id,),
            extra={
                "scorer_ref": spec.scorer_ref,
                "reset_policy": spec.reset_policy,
                "task_source_kind": spec.task_source.kind.value,
            },
        )


class WrappedBenchmarkAdapter(BaseBenchmarkAdapter, ABC):
    def prepare_trial(self, ctx: TrialContext) -> None:
        raise PhaseStubError("WrappedBenchmarkAdapter prepare_trial is a later-phase stub.")

    def seed_environment(self, ctx: TrialContext) -> None:
        raise PhaseStubError("WrappedBenchmarkAdapter seed_environment is a later-phase stub.")

    def get_initial_observation(self, ctx: TrialContext) -> ObservationBundle:
        raise PhaseStubError(
            "WrappedBenchmarkAdapter get_initial_observation is a later-phase stub."
        )


BenchmarkAdapter = BaseBenchmarkAdapter
