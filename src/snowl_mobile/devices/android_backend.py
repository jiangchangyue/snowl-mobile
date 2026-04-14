from __future__ import annotations

import subprocess
import shlex
from dataclasses import dataclass
from typing import Protocol

from snowl_mobile.core.enums import DeviceMode
from snowl_mobile.core.errors import DeviceError
from snowl_mobile.devices.emulator_instance import EmulatorInstance, EmulatorStatus, HealthStatus
from snowl_mobile.devices.emulator_profile import EmulatorProfile
from snowl_mobile.devices.provider import ProviderEvent
from snowl_mobile.schemas.base import SchemaModel


@dataclass(frozen=True, slots=True)
class CommandResult(SchemaModel):
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, argv: tuple[str, ...], *, timeout_sec: int) -> CommandResult:
        ...


class SubprocessCommandRunner:
    def run(self, argv: tuple[str, ...], *, timeout_sec: int) -> CommandResult:
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_sec,
        )
        return CommandResult(
            argv=argv,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


@dataclass(frozen=True, slots=True)
class AdbDeviceRecord(SchemaModel):
    serial: str
    state: str
    model: str
    device: str
    transport_id: str
    avd_name: str


@dataclass(frozen=True, slots=True)
class GrpcPortDiscovery(SchemaModel):
    by_serial: dict[str, int]
    by_avd_name: dict[str, int]


class AndroidEmulatorProvider:
    def __init__(
        self,
        *,
        mode: DeviceMode,
        adb_serials: tuple[str, ...] = (),
        avd_names: tuple[str, ...] = (),
        adb_path: str = "adb",
        emulator_path: str = "emulator",
        command_runner: CommandRunner | None = None,
    ) -> None:
        self.mode = mode
        self.adb_serials = adb_serials
        self.avd_names = avd_names
        self.adb_path = adb_path
        self.emulator_path = emulator_path
        self.command_runner = command_runner or SubprocessCommandRunner()
        self._events: list[ProviderEvent] = []

    def provision_instances(
        self,
        *,
        profile: EmulatorProfile,
        instance_count: int | None,
    ) -> list[EmulatorInstance]:
        discovered = self._discover_candidates(profile=profile)
        if self.mode == DeviceMode.MANAGED_AVD:
            discovered = self._filter_managed_avd_candidates(discovered, profile=profile)

        if not discovered:
            raise DeviceError(
                f"no running Android emulator matched device_mode '{self.mode.value}' "
                f"with adb_serials={list(self.adb_serials)} avd_names={list(self.avd_names)}"
            )

        selected = discovered if instance_count is None else discovered[:instance_count]
        if instance_count is not None and len(selected) < instance_count:
            self._record(
                "capacity_shortfall",
                "pool",
                {
                    "requested_instances": instance_count,
                    "discovered_instances": len(discovered),
                    "selected_instances": len(selected),
                    "device_mode": self.mode.value,
                },
            )
        for instance in selected:
            self.health_check(instance)
            self._record(
                "provisioned",
                instance.instance_id,
                {
                    "adb_serial": instance.adb_serial,
                    "avd_name": instance.avd_name,
                    "device_mode": self.mode.value,
                },
            )
        return selected

    def health_check(self, instance: EmulatorInstance) -> HealthStatus:
        try:
            state_result = self._run(
                (self.adb_path, "-s", instance.adb_serial, "get-state"),
                timeout_sec=15,
            )
        except DeviceError as error:
            instance.mark_health(HealthStatus.UNHEALTHY)
            self._record(
                "health_check",
                instance.instance_id,
                {
                    "health_status": HealthStatus.UNHEALTHY.value,
                    "reason": "adb_get_state_failed",
                    "stderr": self._truncate(str(error)),
                },
            )
            return instance.health_status
        if state_result.returncode != 0:
            instance.mark_health(HealthStatus.UNHEALTHY)
            self._record(
                "health_check",
                instance.instance_id,
                {
                    "health_status": HealthStatus.UNHEALTHY.value,
                    "reason": "adb_get_state_failed",
                    "stderr": self._truncate(state_result.stderr),
                },
            )
            return instance.health_status

        if state_result.stdout.strip() != "device":
            health_status = HealthStatus.UNHEALTHY
            reason = "adb_state_not_device"
        else:
            reason = "boot_probe_ok"
            try:
                boot_result = self._run(
                    (self.adb_path, "-s", instance.adb_serial, "shell", "getprop", "sys.boot_completed"),
                    timeout_sec=15,
                )
            except DeviceError as error:
                health_status = HealthStatus.DEGRADED
                reason = f"boot_probe_failed: {self._truncate(str(error))}"
            else:
                if boot_result.returncode != 0:
                    health_status = HealthStatus.DEGRADED
                    reason = "boot_probe_nonzero"
                elif boot_result.stdout.strip().splitlines()[-1:] == ["1"]:
                    health_status = HealthStatus.HEALTHY
                else:
                    health_status = HealthStatus.DEGRADED
                    reason = "boot_not_completed"
        instance.mark_health(health_status)
        self._record(
            "health_check",
            instance.instance_id,
            {
                "health_status": health_status.value,
                "adb_serial": instance.adb_serial,
                "reason": reason,
            },
        )
        return health_status

    def reset(
        self,
        instance: EmulatorInstance,
        *,
        policy_name: str,
        benchmark_seed_requested: bool,
    ) -> None:
        instance.mark_resetting()
        details: dict[str, object] = {
            "policy_name": policy_name,
            "benchmark_seed_requested": benchmark_seed_requested,
            "device_mode": self.mode.value,
        }
        if policy_name in {"restore_snapshot", "restore_snapshot_then_seed"} and instance.snapshot_name:
            details["snapshot_name"] = instance.snapshot_name
            snapshot_timeout_sec = 20 if self.mode == DeviceMode.EXISTING_DEVICE else 90
            try:
                result = self._run(
                    (
                        self.adb_path,
                        "-s",
                        instance.adb_serial,
                        "emu",
                        "avd",
                        "snapshot",
                        "load",
                        instance.snapshot_name,
                    ),
                    timeout_sec=snapshot_timeout_sec,
                    raise_on_error=False,
                )
            except DeviceError as error:
                details["snapshot_restore_ok"] = False
                details["snapshot_restore_error"] = self._truncate(str(error))
            else:
                details["snapshot_restore_ok"] = result.returncode == 0
                if result.returncode != 0:
                    details["snapshot_restore_error"] = self._truncate(result.stderr or result.stdout)
        if instance.current_trial_id:
            instance.status = EmulatorStatus.LEASED
            instance.touch_heartbeat()
        else:
            instance.mark_idle()
        self._record("reset", instance.instance_id, details)

    def release(self, instance: EmulatorInstance) -> None:
        instance.mark_idle()
        self._record(
            "release",
            instance.instance_id,
            {
                "adb_serial": instance.adb_serial,
                "device_mode": self.mode.value,
            },
        )

    def shutdown(self, instance: EmulatorInstance) -> None:
        details = {
            "adb_serial": instance.adb_serial,
            "device_mode": self.mode.value,
            "shutdown_action": "noop_existing_device",
        }
        if self.mode == DeviceMode.MANAGED_AVD:
            result = self._run((self.adb_path, "-s", instance.adb_serial, "emu", "kill"), timeout_sec=15)
            details["shutdown_action"] = "adb_emu_kill"
            details["shutdown_ok"] = result.returncode == 0
            if result.returncode != 0:
                details["shutdown_error"] = self._truncate(result.stderr or result.stdout)
        instance.mark_shutdown()
        self._record("shutdown", instance.instance_id, details)

    def events(self) -> tuple[ProviderEvent, ...]:
        return tuple(self._events)

    def _discover_candidates(self, *, profile: EmulatorProfile) -> list[EmulatorInstance]:
        devices = self._list_adb_devices()
        grpc_ports = self._discover_existing_device_grpc_ports()
        instances: list[EmulatorInstance] = []
        for device in devices:
            if not self._matches_requested_targets(device):
                continue
            console_port = self._console_port_from_serial(device.serial)
            grpc_port = (
                grpc_ports.by_serial.get(device.serial)
                or grpc_ports.by_avd_name.get(device.avd_name)
                or profile.grpc_port
            )
            instances.append(
                EmulatorInstance(
                    instance_id=device.serial,
                    adb_serial=device.serial,
                    appium_port=self._appium_port_from_console_port(console_port),
                    grpc_port=grpc_port,
                    avd_name=device.avd_name or profile.base_avd_name,
                    snapshot_name=profile.snapshot_name,
                    console_port=console_port or 0,
                    profile_id=profile.profile_id,
                    tags=profile.tags,
                )
            )
        return instances

    def _filter_managed_avd_candidates(
        self,
        instances: list[EmulatorInstance],
        *,
        profile: EmulatorProfile,
    ) -> list[EmulatorInstance]:
        requested_avd_names = self.avd_names or (profile.base_avd_name,)
        filtered = [instance for instance in instances if instance.avd_name in requested_avd_names]
        if filtered:
            return filtered
        self._record(
            "managed_avd_launch_required",
            "pool",
            {
                "requested_avd_names": list(requested_avd_names),
                "message": "automatic managed_avd launch is not implemented in this phase",
            },
        )
        raise DeviceError(
            "managed_avd mode requires a matching running AVD in this phase; "
            "automatic AVD launch is not implemented yet"
        )

    def _list_adb_devices(self) -> list[AdbDeviceRecord]:
        result = self._run((self.adb_path, "devices", "-l"), timeout_sec=20)
        if result.returncode != 0:
            raise DeviceError(f"failed to query adb devices: {self._truncate(result.stderr or result.stdout)}")
        records: list[AdbDeviceRecord] = []
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("List of devices attached"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial = parts[0]
            state = parts[1]
            if not self.adb_serials and not serial.startswith("emulator-"):
                continue
            details: dict[str, str] = {}
            for token in parts[2:]:
                if ":" not in token:
                    continue
                key, value = token.split(":", 1)
                details[key] = value
            records.append(
                AdbDeviceRecord(
                    serial=serial,
                    state=state,
                    model=details.get("model", ""),
                    device=details.get("device", ""),
                    transport_id=details.get("transport_id", ""),
                    avd_name=self._resolve_avd_name(serial),
                )
            )
        self._record(
            "discovery",
            "pool",
            {
                "device_mode": self.mode.value,
                "discovered_serials": [record.serial for record in records],
                "discovered_avd_names": [record.avd_name for record in records],
            },
        )
        return records

    def _resolve_avd_name(self, serial: str) -> str:
        commands = (
            (self.adb_path, "-s", serial, "shell", "getprop", "ro.boot.qemu.avd_name"),
            (self.adb_path, "-s", serial, "shell", "getprop", "persist.sys.avd_name"),
            (self.adb_path, "-s", serial, "emu", "avd", "name"),
        )
        for command in commands:
            try:
                result = self._run(command, timeout_sec=10, raise_on_error=False)
            except DeviceError:
                continue
            if result.returncode != 0:
                continue
            candidate = self._normalize_avd_name(result.stdout)
            if candidate:
                return candidate
        return ""

    def _matches_requested_targets(self, device: AdbDeviceRecord) -> bool:
        if self.adb_serials and device.serial not in self.adb_serials:
            return False
        if self.avd_names and device.avd_name not in self.avd_names:
            return False
        return True

    def _run(
        self,
        argv: tuple[str, ...],
        *,
        timeout_sec: int,
        raise_on_error: bool = True,
    ) -> CommandResult:
        try:
            result = self.command_runner.run(argv, timeout_sec=timeout_sec)
        except subprocess.TimeoutExpired as error:
            hint = ""
            if argv and "adb" in argv[0]:
                hint = (
                    " Check `adb devices` and confirm the target serial stays in state `device` before rerunning."
                )
            raise DeviceError(f"timed out running command: {' '.join(argv)}.{hint}") from error
        if raise_on_error and result.returncode != 0:
            raise DeviceError(self._truncate(result.stderr or result.stdout or f"command failed: {' '.join(argv)}"))
        return result

    def _normalize_avd_name(self, stdout: str) -> str:
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        filtered = [line for line in lines if line.upper() != "OK"]
        return filtered[-1] if filtered else ""

    def _console_port_from_serial(self, serial: str) -> int | None:
        if not serial.startswith("emulator-"):
            return None
        suffix = serial.removeprefix("emulator-").strip()
        if not suffix.isdigit():
            return None
        return int(suffix)

    def _appium_port_from_console_port(self, console_port: int | None) -> int:
        if not console_port or console_port < 5554:
            return 4723
        slot = max((console_port - 5554) // 2, 0)
        return 4723 + slot

    def _discover_existing_device_grpc_ports(self) -> GrpcPortDiscovery:
        try:
            result = self.command_runner.run(
                ("ps", "-axww", "-o", "pid=,command="),
                timeout_sec=20,
            )
        except Exception:
            return GrpcPortDiscovery(by_serial={}, by_avd_name={})
        if result.returncode != 0:
            return GrpcPortDiscovery(by_serial={}, by_avd_name={})

        by_serial: dict[str, int] = {}
        avd_candidates: dict[str, set[int]] = {}
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                _pid, command = line.split(None, 1)
            except ValueError:
                continue
            if "-grpc" not in command:
                continue
            avd_name = self._extract_flag_value(command, "-avd")
            grpc_port = self._extract_flag_value(command, "-grpc")
            if not avd_name or not grpc_port or not grpc_port.isdigit():
                continue
            grpc_port_int = int(grpc_port)
            console_port = self._extract_console_port_from_emulator_command(command)
            if console_port is not None:
                by_serial[f"emulator-{console_port}"] = grpc_port_int
            avd_candidates.setdefault(avd_name, set()).add(grpc_port_int)
        by_avd_name = {
            avd_name: next(iter(ports))
            for avd_name, ports in avd_candidates.items()
            if len(ports) == 1
        }
        return GrpcPortDiscovery(by_serial=by_serial, by_avd_name=by_avd_name)

    def _extract_flag_value(self, command: str, flag: str) -> str:
        try:
            tokens = shlex.split(command)
        except ValueError:
            tokens = command.split()
        for index, token in enumerate(tokens):
            if token == flag and index + 1 < len(tokens):
                return tokens[index + 1].strip()
            if token.startswith(f"{flag}="):
                return token.split("=", 1)[1].strip()
        return ""

    def _extract_console_port_from_emulator_command(self, command: str) -> int | None:
        port_value = self._extract_flag_value(command, "-port")
        if port_value.isdigit():
            return int(port_value)
        ports_value = self._extract_flag_value(command, "-ports")
        if ports_value:
            first_port = ports_value.split(",", 1)[0].strip()
            if first_port.isdigit():
                return int(first_port)
        return None

    def _record(self, event: str, instance_id: str, details: dict[str, object]) -> None:
        self._events.append(ProviderEvent(event=event, instance_id=instance_id, details=details))

    def _truncate(self, value: str, limit: int = 200) -> str:
        text = value.strip()
        if len(text) <= limit:
            return text
        return f"{text[: limit - 3]}..."
