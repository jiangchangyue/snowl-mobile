from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.devices.android_ports import (  # noqa: E402
    console_port_from_adb_serial,
    resolve_androidworld_console_port,
    resolve_androidworld_grpc_port,
)
from snowl_mobile.devices.emulator_instance import EmulatorInstance  # noqa: E402


class AndroidWorldDevicePortsTestCase(unittest.TestCase):
    def test_console_port_from_adb_serial_derives_console_suffix(self) -> None:
        self.assertEqual(console_port_from_adb_serial("emulator-5562"), 5562)
        self.assertIsNone(console_port_from_adb_serial("device-1234"))

    def test_resolve_androidworld_console_port_prefers_instance_console_port(self) -> None:
        emulator = EmulatorInstance(
            instance_id="emulator-5562",
            adb_serial="emulator-5562",
            appium_port=0,
            grpc_port=8554,
            avd_name="AndroidWorldAvd2",
            snapshot_name="androidworld_base",
            console_port=5562,
        )

        resolved = resolve_androidworld_console_port(
            emulator_instance=emulator,
            runtime_recipe_ports={"console_port": 5554},
            benchmark_options={"console_port": 5554},
        )

        self.assertEqual(resolved, 5562)

    def test_resolve_androidworld_console_port_falls_back_to_adb_serial_suffix(self) -> None:
        emulator = EmulatorInstance(
            instance_id="emulator-5562",
            adb_serial="emulator-5562",
            appium_port=0,
            grpc_port=8554,
            avd_name="AndroidWorldAvd2",
            snapshot_name="androidworld_base",
        )

        resolved = resolve_androidworld_console_port(
            emulator_instance=emulator,
            runtime_recipe_ports={"console_port": 5554},
            benchmark_options={"console_port": 5554},
        )

        self.assertEqual(resolved, 5562)

    def test_resolve_androidworld_grpc_port_prefers_instance_grpc_port(self) -> None:
        emulator = EmulatorInstance(
            instance_id="emulator-5556",
            adb_serial="emulator-5556",
            appium_port=0,
            grpc_port=8556,
            avd_name="AndroidWorldAvd",
            snapshot_name="androidworld_base",
            console_port=5556,
        )

        resolved = resolve_androidworld_grpc_port(
            emulator_instance=emulator,
            runtime_recipe_ports={"grpc_port": 8554},
            benchmark_options={"grpc_port": 8554},
        )

        self.assertEqual(resolved, 8556)


if __name__ == "__main__":
    unittest.main()
