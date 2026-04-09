from __future__ import annotations

from dataclasses import dataclass

from snowl_mobile.core.enums import DeviceMode
from snowl_mobile.core.errors import DeviceError, SchedulerError
from snowl_mobile.core.trial_spec import TrialSpec
from snowl_mobile.devices.android_backend import AndroidEmulatorProvider, CommandRunner
from snowl_mobile.devices.emulator_instance import (
    EmulatorInstance,
    EmulatorLease,
    EmulatorStatus,
    HealthStatus,
    utcnow_iso,
)
from snowl_mobile.devices.emulator_profile import EmulatorProfile
from snowl_mobile.devices.provider import EmulatorProvider, ProviderEvent
from snowl_mobile.schemas.base import SchemaModel


@dataclass(frozen=True, slots=True)
class EmulatorPoolSnapshot(SchemaModel):
    total_instances: int
    idle_instances: int
    leased_instances: int
    resetting_instances: int
    offline_instances: int
    healthy_instances: int
    unhealthy_instances: int


class FakeEmulatorProvider:
    """In-memory emulator provider used to exercise pool logic without adb/emulator."""

    def __init__(self) -> None:
        self._health_overrides: dict[str, HealthStatus] = {}
        self._events: list[ProviderEvent] = []

    def provision_instances(
        self,
        *,
        profile: EmulatorProfile,
        instance_count: int | None,
    ) -> list[EmulatorInstance]:
        requested_count = instance_count or 1
        base_adb_port = 5554
        base_appium_port = 4723
        base_grpc_port = profile.grpc_port
        instances: list[EmulatorInstance] = []
        for index in range(requested_count):
            instance = EmulatorInstance(
                instance_id=f"{profile.profile_id}-{index + 1:02d}",
                adb_serial=f"emulator-{base_adb_port + (index * 2)}",
                appium_port=base_appium_port + index,
                grpc_port=base_grpc_port + index,
                avd_name=f"{profile.base_avd_name}_{index + 1:02d}",
                snapshot_name=profile.snapshot_name,
                profile_id=profile.profile_id,
                tags=profile.tags,
            )
            instance.mark_health(HealthStatus.HEALTHY)
            self._record("provisioned", instance.instance_id, {"profile_id": profile.profile_id})
            instances.append(instance)
        return instances

    def health_check(self, instance: EmulatorInstance) -> HealthStatus:
        status = self._health_overrides.get(instance.instance_id, HealthStatus.HEALTHY)
        instance.mark_health(status)
        self._record("health_check", instance.instance_id, {"health_status": status.value})
        return status

    def set_health(self, instance_id: str, health_status: HealthStatus) -> None:
        self._health_overrides[instance_id] = health_status
        self._record("health_override", instance_id, {"health_status": health_status.value})

    def reset(self, instance: EmulatorInstance, *, policy_name: str, benchmark_seed_requested: bool) -> None:
        instance.mark_resetting()
        self._record(
            "reset",
            instance.instance_id,
            {
                "policy_name": policy_name,
                "benchmark_seed_requested": benchmark_seed_requested,
            },
        )
        if instance.health_status != HealthStatus.UNHEALTHY:
            if instance.current_trial_id:
                instance.status = EmulatorStatus.LEASED
                instance.touch_heartbeat()
            else:
                instance.mark_idle()

    def release(self, instance: EmulatorInstance) -> None:
        instance.mark_idle()
        self._record("release", instance.instance_id, {})

    def shutdown(self, instance: EmulatorInstance) -> None:
        instance.mark_shutdown()
        self._record("shutdown", instance.instance_id, {})

    def events(self) -> tuple[ProviderEvent, ...]:
        return tuple(self._events)

    def _record(self, event: str, instance_id: str, details: dict[str, object]) -> None:
        self._events.append(
            ProviderEvent(
                event=event,
                instance_id=instance_id,
                details=details,
            )
        )


class EmulatorPoolManager:
    def __init__(self, *, provider: EmulatorProvider | None = None) -> None:
        self.provider = provider or FakeEmulatorProvider()
        self._instances: dict[str, EmulatorInstance] = {}
        self._leases: dict[str, EmulatorLease] = {}

    def provision_pool(
        self,
        *,
        profile: EmulatorProfile,
        instance_count: int | None,
    ) -> tuple[EmulatorInstance, ...]:
        for instance in self.provider.provision_instances(profile=profile, instance_count=instance_count):
            self._instances[instance.instance_id] = instance
        return self.instances()

    def instances(self) -> tuple[EmulatorInstance, ...]:
        return tuple(self._instances[key] for key in sorted(self._instances))

    def available_instances(self, *, profile_id: str | None = None) -> list[EmulatorInstance]:
        instances = [
            instance
            for instance in self._instances.values()
            if instance.is_available and (profile_id is None or instance.profile_id == profile_id)
        ]
        return sorted(instances, key=lambda instance: instance.instance_id)

    def assign_trial(self, trial_spec: TrialSpec) -> EmulatorLease | None:
        return self.acquire_lease(
            trial_id=trial_spec.trial_id,
            profile_id=trial_spec.runtime_recipe.device_profile,
        )

    def acquire_lease(self, *, trial_id: str, profile_id: str | None = None) -> EmulatorLease | None:
        for instance in self.available_instances(profile_id=profile_id):
            if self.provider.health_check(instance) == HealthStatus.UNHEALTHY:
                continue
            instance.mark_leased(trial_id)
            lease = EmulatorLease(
                lease_id=f"{trial_id}@{instance.instance_id}",
                instance_id=instance.instance_id,
                trial_id=trial_id,
                adb_serial=instance.adb_serial,
                profile_id=instance.profile_id,
                acquired_at=utcnow_iso(),
            )
            self._leases[lease.lease_id] = lease
            return lease
        return None

    def release_instance(self, lease: EmulatorLease) -> EmulatorInstance:
        instance = self._require_instance(lease.instance_id)
        self._leases.pop(lease.lease_id, None)
        self.provider.release(instance)
        return instance

    def health_check(self, instance_id: str) -> HealthStatus:
        instance = self._require_instance(instance_id)
        return self.provider.health_check(instance)

    def set_health(self, instance_id: str, health_status: HealthStatus) -> None:
        if not hasattr(self.provider, "set_health"):
            raise DeviceError("active emulator provider does not support manual health overrides")
        self.provider.set_health(instance_id, health_status)
        instance = self._require_instance(instance_id)
        instance.mark_health(health_status)

    def restart_instance(self, instance_id: str) -> EmulatorInstance:
        instance = self._require_instance(instance_id)
        instance.mark_health(HealthStatus.HEALTHY)
        instance.mark_idle()
        return instance

    def shutdown_all(self) -> None:
        for instance in self._instances.values():
            self.provider.shutdown(instance)
        self._leases.clear()

    def active_leases(self) -> tuple[EmulatorLease, ...]:
        return tuple(self._leases[key] for key in sorted(self._leases))

    def get_instance(self, instance_id: str) -> EmulatorInstance:
        return self._require_instance(instance_id)

    def snapshot(self) -> EmulatorPoolSnapshot:
        instances = list(self._instances.values())
        return EmulatorPoolSnapshot(
            total_instances=len(instances),
            idle_instances=sum(instance.status == EmulatorStatus.IDLE for instance in instances),
            leased_instances=sum(instance.status == EmulatorStatus.LEASED for instance in instances),
            resetting_instances=sum(instance.status == EmulatorStatus.RESETTING for instance in instances),
            offline_instances=sum(instance.status == EmulatorStatus.OFFLINE for instance in instances),
            healthy_instances=sum(instance.health_status == HealthStatus.HEALTHY for instance in instances),
            unhealthy_instances=sum(instance.health_status == HealthStatus.UNHEALTHY for instance in instances),
        )

    def provider_events(self) -> tuple[ProviderEvent, ...]:
        return self.provider.events()

    def _require_instance(self, instance_id: str) -> EmulatorInstance:
        try:
            return self._instances[instance_id]
        except KeyError as error:
            raise SchedulerError(f"unknown emulator instance '{instance_id}'") from error


FakeProviderEvent = ProviderEvent


def create_emulator_pool_manager(
    *,
    device_mode: DeviceMode,
    adb_serials: tuple[str, ...] = (),
    avd_names: tuple[str, ...] = (),
    command_runner: CommandRunner | None = None,
) -> EmulatorPoolManager:
    if device_mode == DeviceMode.FAKE:
        return EmulatorPoolManager(provider=FakeEmulatorProvider())
    return EmulatorPoolManager(
        provider=AndroidEmulatorProvider(
            mode=device_mode,
            adb_serials=adb_serials,
            avd_names=avd_names,
            command_runner=command_runner,
        )
    )
