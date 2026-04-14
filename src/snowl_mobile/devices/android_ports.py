from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from snowl_mobile.devices.emulator_instance import EmulatorInstance


def console_port_from_adb_serial(adb_serial: str) -> int | None:
    if not adb_serial.startswith("emulator-"):
        return None
    suffix = adb_serial.removeprefix("emulator-").strip()
    if not suffix.isdigit():
        return None
    return int(suffix)


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def resolve_androidworld_console_port(
    *,
    emulator_instance: EmulatorInstance,
    runtime_recipe_ports: Mapping[str, int] | None = None,
    benchmark_options: Mapping[str, Any] | None = None,
) -> int:
    explicit_console_port = _int_or_none(getattr(emulator_instance, "console_port", None))
    if explicit_console_port and explicit_console_port > 0:
        return explicit_console_port

    derived_console_port = console_port_from_adb_serial(emulator_instance.adb_serial)
    if derived_console_port and derived_console_port > 0:
        return derived_console_port

    if runtime_recipe_ports is not None:
        recipe_console_port = _int_or_none(runtime_recipe_ports.get("console_port"))
        if recipe_console_port and recipe_console_port > 0:
            return recipe_console_port

    if benchmark_options is not None:
        benchmark_console_port = _int_or_none(benchmark_options.get("console_port"))
        if benchmark_console_port and benchmark_console_port > 0:
            return benchmark_console_port

    return 5554


def resolve_androidworld_grpc_port(
    *,
    emulator_instance: EmulatorInstance,
    runtime_recipe_ports: Mapping[str, int] | None = None,
    benchmark_options: Mapping[str, Any] | None = None,
) -> int:
    explicit_grpc_port = _int_or_none(getattr(emulator_instance, "grpc_port", None))
    if explicit_grpc_port and explicit_grpc_port > 0:
        return explicit_grpc_port

    if runtime_recipe_ports is not None:
        recipe_grpc_port = _int_or_none(runtime_recipe_ports.get("grpc_port"))
        if recipe_grpc_port and recipe_grpc_port > 0:
            return recipe_grpc_port

    if benchmark_options is not None:
        benchmark_grpc_port = _int_or_none(benchmark_options.get("grpc_port"))
        if benchmark_grpc_port and benchmark_grpc_port > 0:
            return benchmark_grpc_port

    return 8554

