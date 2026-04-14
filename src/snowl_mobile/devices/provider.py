from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from snowl_mobile.devices.emulator_instance import EmulatorInstance, HealthStatus, utcnow_iso
from snowl_mobile.devices.emulator_profile import EmulatorProfile
from snowl_mobile.schemas.base import SchemaModel


@dataclass(frozen=True, slots=True)
class ProviderEvent(SchemaModel):
    event: str
    instance_id: str
    timestamp: str = field(default_factory=utcnow_iso)
    details: dict[str, object] = field(default_factory=dict)


class EmulatorProvider(Protocol):
    def provision_instances(
        self,
        *,
        profile: EmulatorProfile,
        instance_count: int | None,
    ) -> list[EmulatorInstance]:
        ...

    def health_check(self, instance: EmulatorInstance) -> HealthStatus:
        ...

    def reset(
        self,
        instance: EmulatorInstance,
        *,
        policy_name: str,
        benchmark_seed_requested: bool,
    ) -> None:
        ...

    def release(self, instance: EmulatorInstance) -> None:
        ...

    def shutdown(self, instance: EmulatorInstance) -> None:
        ...

    def events(self) -> tuple[ProviderEvent, ...]:
        ...
