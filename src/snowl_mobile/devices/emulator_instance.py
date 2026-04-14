from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum

from snowl_mobile.schemas.base import SchemaModel


def utcnow_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class HealthStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


class EmulatorStatus(StrEnum):
    UNINITIALIZED = "UNINITIALIZED"
    IDLE = "IDLE"
    LEASED = "LEASED"
    RESETTING = "RESETTING"
    OFFLINE = "OFFLINE"
    SHUTDOWN = "SHUTDOWN"


@dataclass(slots=True)
class EmulatorInstance(SchemaModel):
    instance_id: str
    adb_serial: str
    appium_port: int
    grpc_port: int
    avd_name: str
    snapshot_name: str
    console_port: int = 0
    status: EmulatorStatus = EmulatorStatus.UNINITIALIZED
    current_trial_id: str | None = None
    last_heartbeat_at: str | None = None
    health_status: HealthStatus = HealthStatus.UNKNOWN
    profile_id: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_available(self) -> bool:
        return self.status == EmulatorStatus.IDLE and self.health_status != HealthStatus.UNHEALTHY

    def mark_idle(self) -> None:
        self.status = EmulatorStatus.IDLE
        self.current_trial_id = None
        self.touch_heartbeat()

    def mark_leased(self, trial_id: str) -> None:
        self.status = EmulatorStatus.LEASED
        self.current_trial_id = trial_id
        self.touch_heartbeat()

    def mark_resetting(self) -> None:
        self.status = EmulatorStatus.RESETTING
        self.touch_heartbeat()

    def mark_shutdown(self) -> None:
        self.status = EmulatorStatus.SHUTDOWN
        self.current_trial_id = None
        self.touch_heartbeat()

    def mark_health(self, health_status: HealthStatus) -> None:
        self.health_status = health_status
        if health_status == HealthStatus.UNHEALTHY and self.status != EmulatorStatus.LEASED:
            self.status = EmulatorStatus.OFFLINE
        elif health_status in {HealthStatus.HEALTHY, HealthStatus.DEGRADED} and self.status in {
            EmulatorStatus.UNINITIALIZED,
            EmulatorStatus.OFFLINE,
        }:
            self.status = EmulatorStatus.IDLE
        self.touch_heartbeat()

    def touch_heartbeat(self) -> None:
        self.last_heartbeat_at = utcnow_iso()


@dataclass(frozen=True, slots=True)
class EmulatorLease(SchemaModel):
    lease_id: str
    instance_id: str
    trial_id: str
    adb_serial: str
    profile_id: str
    acquired_at: str
