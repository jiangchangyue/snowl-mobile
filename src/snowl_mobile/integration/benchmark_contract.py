from __future__ import annotations

from dataclasses import dataclass

from snowl_mobile.core.errors import IntegrationError


@dataclass(frozen=True, slots=True)
class NativeMetricMapping:
    native_metric: str
    platform_metric: str
    rationale: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "native_metric": self.native_metric,
            "platform_metric": self.platform_metric,
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkAdapterContract:
    task_discovery_entry: str
    environment_init_entry: str
    pre_task_setup_entry: str
    reset_entry: str
    run_entry: str
    score_capture_entry: str
    cleanup_entry: str
    observation_form: str
    action_execution_path: str
    raw_artifact_capture_points: tuple[str, ...]
    native_metric_mappings: tuple[NativeMetricMapping, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "task_discovery_entry": self.task_discovery_entry,
            "environment_init_entry": self.environment_init_entry,
            "pre_task_setup_entry": self.pre_task_setup_entry,
            "reset_entry": self.reset_entry,
            "run_entry": self.run_entry,
            "score_capture_entry": self.score_capture_entry,
            "cleanup_entry": self.cleanup_entry,
            "observation_form": self.observation_form,
            "action_execution_path": self.action_execution_path,
            "raw_artifact_capture_points": list(self.raw_artifact_capture_points),
            "native_metric_mappings": [
                mapping.to_dict() for mapping in self.native_metric_mappings
            ],
        }


class BenchmarkContractValidator:
    """Validate the structure of a benchmark integration contract."""

    def validate(self, contract: BenchmarkAdapterContract) -> BenchmarkAdapterContract:
        required_fields = {
            "task_discovery_entry": contract.task_discovery_entry,
            "environment_init_entry": contract.environment_init_entry,
            "pre_task_setup_entry": contract.pre_task_setup_entry,
            "reset_entry": contract.reset_entry,
            "run_entry": contract.run_entry,
            "score_capture_entry": contract.score_capture_entry,
            "cleanup_entry": contract.cleanup_entry,
            "observation_form": contract.observation_form,
            "action_execution_path": contract.action_execution_path,
        }
        missing = sorted(name for name, value in required_fields.items() if not value.strip())
        if missing:
            joined = ", ".join(missing)
            raise IntegrationError(f"benchmark contract is missing required fields: {joined}")
        if not contract.raw_artifact_capture_points:
            raise IntegrationError("benchmark contract requires at least one raw_artifact_capture_point")
        if not contract.native_metric_mappings:
            raise IntegrationError("benchmark contract requires at least one native metric mapping")

        seen_native: set[str] = set()
        seen_platform: set[str] = set()
        for mapping in contract.native_metric_mappings:
            if not mapping.native_metric.strip() or not mapping.platform_metric.strip():
                raise IntegrationError("native metric mappings must use non-empty metric names")
            if mapping.native_metric in seen_native:
                raise IntegrationError(
                    f"duplicate native metric mapping for '{mapping.native_metric}'"
                )
            if mapping.platform_metric in seen_platform:
                raise IntegrationError(
                    f"duplicate platform metric mapping for '{mapping.platform_metric}'"
                )
            seen_native.add(mapping.native_metric)
            seen_platform.add(mapping.platform_metric)
        return contract
