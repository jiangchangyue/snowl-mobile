"""Device management shells."""

from snowl_mobile.devices.android_backend import AndroidEmulatorProvider
from snowl_mobile.devices.emulator_instance import (
    EmulatorInstance,
    EmulatorLease,
    EmulatorStatus,
    HealthStatus,
)
from snowl_mobile.devices.emulator_pool import (
    EmulatorPoolManager,
    FakeEmulatorProvider,
    create_emulator_pool_manager,
)
from snowl_mobile.devices.reset_strategy import ResetManager, ResetRecord, ResetStrategyName

__all__ = [
    "AndroidEmulatorProvider",
    "EmulatorInstance",
    "EmulatorLease",
    "EmulatorStatus",
    "HealthStatus",
    "EmulatorPoolManager",
    "FakeEmulatorProvider",
    "create_emulator_pool_manager",
    "ResetManager",
    "ResetRecord",
    "ResetStrategyName",
]
