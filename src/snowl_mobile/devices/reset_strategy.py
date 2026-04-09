from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from snowl_mobile.core.policies import ResetPolicy
from snowl_mobile.devices.emulator_instance import EmulatorLease, utcnow_iso
from snowl_mobile.devices.emulator_pool import EmulatorPoolManager
from snowl_mobile.schemas.base import SchemaModel


class ResetStrategyName(StrEnum):
    NONE = "none"
    RESTORE_SNAPSHOT = "restore_snapshot"
    BENCHMARK_NATIVE_RESET = "benchmark_native_reset"
    RESTORE_SNAPSHOT_THEN_SEED = "restore_snapshot_then_seed"


@dataclass(frozen=True, slots=True)
class ResetRecord(SchemaModel):
    lease_id: str
    instance_id: str
    trial_id: str
    strategy: str
    benchmark_seed_requested: bool
    snapshot_restored: bool
    notes: tuple[str, ...] = field(default_factory=tuple)
    executed_at: str = field(default_factory=utcnow_iso)


class ResetManager:
    def __init__(self, *, policy: ResetPolicy) -> None:
        self.policy = policy
        self._records: list[ResetRecord] = []

    def reset_for_trial(
        self,
        *,
        pool_manager: EmulatorPoolManager,
        lease: EmulatorLease,
        benchmark_reset_policy: str,
        benchmark_requires_seed: bool = False,
    ) -> ResetRecord:
        strategy = self.normalize_policy_name(benchmark_reset_policy)
        benchmark_seed_requested = (
            strategy in {
                ResetStrategyName.BENCHMARK_NATIVE_RESET,
                ResetStrategyName.RESTORE_SNAPSHOT_THEN_SEED,
            }
            and self.policy.allow_benchmark_seed
            and benchmark_requires_seed
        )
        snapshot_restored = strategy in {
            ResetStrategyName.RESTORE_SNAPSHOT,
            ResetStrategyName.RESTORE_SNAPSHOT_THEN_SEED,
        }

        if strategy != ResetStrategyName.NONE:
            pool_manager.provider.reset(
                pool_manager.get_instance(lease.instance_id),
                policy_name=strategy.value,
                benchmark_seed_requested=benchmark_seed_requested,
            )

        record = ResetRecord(
            lease_id=lease.lease_id,
            instance_id=lease.instance_id,
            trial_id=lease.trial_id,
            strategy=strategy.value,
            benchmark_seed_requested=benchmark_seed_requested,
            snapshot_restored=snapshot_restored,
            notes=self._notes_for_strategy(strategy, benchmark_seed_requested),
        )
        self._records.append(record)
        return record

    def records(self) -> tuple[ResetRecord, ...]:
        return tuple(self._records)

    def normalize_policy_name(self, policy_name: str) -> ResetStrategyName:
        aliases = {
            "none": ResetStrategyName.NONE,
            "restore_snapshot": ResetStrategyName.RESTORE_SNAPSHOT,
            "benchmark_native_reset": ResetStrategyName.BENCHMARK_NATIVE_RESET,
            "restore_snapshot_then_seed": ResetStrategyName.RESTORE_SNAPSHOT_THEN_SEED,
            "snapshot_then_seed": ResetStrategyName.RESTORE_SNAPSHOT_THEN_SEED,
        }
        return aliases.get(policy_name, ResetStrategyName.RESTORE_SNAPSHOT_THEN_SEED)

    def _notes_for_strategy(
        self,
        strategy: ResetStrategyName,
        benchmark_seed_requested: bool,
    ) -> tuple[str, ...]:
        notes: list[str] = []
        if strategy == ResetStrategyName.NONE:
            notes.append("no device reset requested")
        if strategy in {
            ResetStrategyName.RESTORE_SNAPSHOT,
            ResetStrategyName.RESTORE_SNAPSHOT_THEN_SEED,
        }:
            notes.append(f"restore snapshot '{self.policy.baseline_snapshot}'")
        if benchmark_seed_requested:
            notes.append("benchmark seeding requested but not executed in this phase")
        return tuple(notes)
