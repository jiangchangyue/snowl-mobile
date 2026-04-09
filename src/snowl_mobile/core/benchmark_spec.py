from __future__ import annotations

from dataclasses import dataclass, field

from snowl_mobile.core.enums import IntegrationMode, TaskSourceKind
from snowl_mobile.core.validation import (
    expect_enum_member,
    expect_mapping,
    expect_string,
    expect_string_list,
    get_optional,
    get_required,
)
from snowl_mobile.schemas.base import SchemaModel


@dataclass(frozen=True, slots=True)
class TaskSourceSpec(SchemaModel):
    kind: TaskSourceKind
    path: str = ""
    selector: str = ""
    manifest: str = ""

    @classmethod
    def from_mapping(cls, data: dict[str, object], path: str) -> "TaskSourceSpec":
        return cls(
            kind=expect_enum_member(get_required(data, "kind", path), f"{path}.kind", TaskSourceKind),
            path=expect_string(get_optional(data, "path", ""), f"{path}.path", allow_empty=True),
            selector=expect_string(
                get_optional(data, "selector", ""),
                f"{path}.selector",
                allow_empty=True,
            ),
            manifest=expect_string(
                get_optional(data, "manifest", ""),
                f"{path}.manifest",
                allow_empty=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class MetricSchemaSpec(SchemaModel):
    primary_metric: str
    native_metrics: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, data: dict[str, object], path: str) -> "MetricSchemaSpec":
        return cls(
            primary_metric=expect_string(
                get_required(data, "primary_metric", path, aliases=("primary",)),
                f"{path}.primary_metric",
            ),
            native_metrics=expect_string_list(
                get_optional(data, "native_metrics", get_optional(data, "native", [])),
                f"{path}.native_metrics",
            ),
        )


@dataclass(frozen=True, slots=True)
class BenchmarkSpec(SchemaModel):
    benchmark_id: str
    display_name: str
    integration_mode: IntegrationMode
    task_source: TaskSourceSpec
    metric_schema: MetricSchemaSpec
    scorer_ref: str
    reset_policy: str
    reset_requirements: dict[str, object]
    device_backend: str
    required_env: tuple[str, ...]
    supported_agent_ids: tuple[str, ...]
    options: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict[str, object], path: str) -> "BenchmarkSpec":
        task_source_data = expect_mapping(get_required(data, "task_source", path), f"{path}.task_source")
        metric_schema_data = expect_mapping(
            get_required(data, "metric_schema", path),
            f"{path}.metric_schema",
        )
        reset_requirements = expect_mapping(
            get_optional(data, "reset_requirements", {}),
            f"{path}.reset_requirements",
        )
        options = expect_mapping(
            get_optional(data, "options", {}),
            f"{path}.options",
        )
        return cls(
            benchmark_id=expect_string(
                get_required(data, "benchmark_id", path, aliases=("id",)),
                f"{path}.benchmark_id",
            ),
            display_name=expect_string(
                get_optional(
                    data,
                    "display_name",
                    get_required(data, "benchmark_id", path, aliases=("id",)),
                ),
                f"{path}.display_name",
            ),
            integration_mode=expect_enum_member(
                get_optional(data, "integration_mode", IntegrationMode.WRAP.value),
                f"{path}.integration_mode",
                IntegrationMode,
            ),
            task_source=TaskSourceSpec.from_mapping(task_source_data, f"{path}.task_source"),
            metric_schema=MetricSchemaSpec.from_mapping(metric_schema_data, f"{path}.metric_schema"),
            scorer_ref=expect_string(get_required(data, "scorer_ref", path), f"{path}.scorer_ref"),
            reset_policy=expect_string(
                get_required(data, "reset_policy", path),
                f"{path}.reset_policy",
            ),
            reset_requirements=reset_requirements,
            device_backend=expect_string(
                get_required(data, "device_backend", path),
                f"{path}.device_backend",
            ),
            required_env=expect_string_list(
                get_optional(data, "required_env", []),
                f"{path}.required_env",
            ),
            supported_agent_ids=expect_string_list(
                get_optional(data, "supported_agent_ids", []),
                f"{path}.supported_agent_ids",
            ),
            options=options,
        )
