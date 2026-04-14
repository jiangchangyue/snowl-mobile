from __future__ import annotations

from dataclasses import dataclass

from snowl_mobile.core.enums import ArtifactLevel, ResetScope
from snowl_mobile.core.validation import (
    expect_bool,
    expect_enum_member,
    expect_int,
    expect_string,
    expect_string_list,
    get_optional,
    get_required,
)
from snowl_mobile.schemas.base import SchemaModel


@dataclass(frozen=True, slots=True)
class RetryPolicy(SchemaModel):
    max_trial_retries: int = 0
    max_step_retries: int = 0
    backoff_sec: int = 0
    retry_on: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, data: dict[str, object], path: str) -> "RetryPolicy":
        return cls(
            max_trial_retries=expect_int(
                get_optional(data, "max_trial_retries", 0), f"{path}.max_trial_retries", minimum=0
            ),
            max_step_retries=expect_int(
                get_optional(data, "max_step_retries", 0), f"{path}.max_step_retries", minimum=0
            ),
            backoff_sec=expect_int(
                get_optional(data, "backoff_sec", 0), f"{path}.backoff_sec", minimum=0
            ),
            retry_on=expect_string_list(get_optional(data, "retry_on", []), f"{path}.retry_on"),
        )


@dataclass(frozen=True, slots=True)
class ResetPolicy(SchemaModel):
    name: str
    scope: ResetScope
    baseline_snapshot: str
    allow_benchmark_seed: bool = True
    healthcheck_timeout_sec: int = 120

    @classmethod
    def from_mapping(cls, data: dict[str, object], path: str) -> "ResetPolicy":
        return cls(
            name=expect_string(get_required(data, "name", path), f"{path}.name"),
            scope=expect_enum_member(
                get_optional(data, "scope", ResetScope.TRIAL.value),
                f"{path}.scope",
                ResetScope,
            ),
            baseline_snapshot=expect_string(
                get_required(data, "baseline_snapshot", path), f"{path}.baseline_snapshot"
            ),
            allow_benchmark_seed=expect_bool(
                get_optional(data, "allow_benchmark_seed", True),
                f"{path}.allow_benchmark_seed",
            ),
            healthcheck_timeout_sec=expect_int(
                get_optional(data, "healthcheck_timeout_sec", 120),
                f"{path}.healthcheck_timeout_sec",
                minimum=1,
            ),
        )


@dataclass(frozen=True, slots=True)
class ArtifactPolicy(SchemaModel):
    level: ArtifactLevel
    root_dir: str
    persist_step_artifacts: bool = True
    persist_logs: bool = True
    persist_prompt_payloads: bool = False

    @classmethod
    def from_mapping(cls, data: dict[str, object], path: str) -> "ArtifactPolicy":
        return cls(
            level=expect_enum_member(get_optional(data, "level", "standard"), f"{path}.level", ArtifactLevel),
            root_dir=expect_string(get_optional(data, "root_dir", "runs"), f"{path}.root_dir"),
            persist_step_artifacts=expect_bool(
                get_optional(data, "persist_step_artifacts", True),
                f"{path}.persist_step_artifacts",
            ),
            persist_logs=expect_bool(get_optional(data, "persist_logs", True), f"{path}.persist_logs"),
            persist_prompt_payloads=expect_bool(
                get_optional(data, "persist_prompt_payloads", False),
                f"{path}.persist_prompt_payloads",
            ),
        )
