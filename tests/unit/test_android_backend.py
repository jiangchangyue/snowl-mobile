from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.core.enums import DeviceMode
from snowl_mobile.core.errors import DeviceError
from snowl_mobile.devices.android_backend import AndroidEmulatorProvider, CommandResult
from snowl_mobile.devices.emulator_instance import EmulatorInstance
from snowl_mobile.devices.emulator_profile import EmulatorProfile


class FakeCommandRunner:
    def __init__(self, responses: dict[tuple[str, ...], CommandResult]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], *, timeout_sec: int) -> CommandResult:
        del timeout_sec
        self.calls.append(argv)
        try:
            response = self.responses[argv]
        except KeyError as error:
            raise AssertionError(f"unexpected command: {' '.join(argv)}") from error
        if isinstance(response, Exception):
            raise response
        return response


class AndroidBackendTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = EmulatorProfile(
            profile_id="api34_base",
            base_avd_name="Pixel_6_API_34",
            platform="android",
            api_level=34,
            system_image="android-34/google_apis/x86_64",
            snapshot_name="clean-base",
            screen_size="1080x2400",
            grpc_port=8554,
            tags=("baseline",),
        )

    def test_existing_device_provider_discovers_and_health_checks_running_emulators(self) -> None:
        responses = {
            ("adb", "devices", "-l"): CommandResult(
                argv=("adb", "devices", "-l"),
                returncode=0,
                stdout=(
                    "List of devices attached\n"
                    "emulator-5554 device product:sdk_gphone64_arm64 "
                    "model:sdk_gphone64_arm64 device:emu64a transport_id:32\n"
                    "emulator-5556 device product:sdk_gphone64_arm64 "
                    "model:sdk_gphone64_arm64 device:emu64a transport_id:33\n"
                ),
                stderr="",
            ),
            ("adb", "-s", "emulator-5554", "shell", "getprop", "ro.boot.qemu.avd_name"): CommandResult(
                argv=("adb", "-s", "emulator-5554", "shell", "getprop", "ro.boot.qemu.avd_name"),
                returncode=0,
                stdout="Pixel_6_API_34\n",
                stderr="",
            ),
            ("adb", "-s", "emulator-5556", "shell", "getprop", "ro.boot.qemu.avd_name"): CommandResult(
                argv=("adb", "-s", "emulator-5556", "shell", "getprop", "ro.boot.qemu.avd_name"),
                returncode=0,
                stdout="Pixel_7_API_34\n",
                stderr="",
            ),
            ("adb", "-s", "emulator-5554", "get-state"): CommandResult(
                argv=("adb", "-s", "emulator-5554", "get-state"),
                returncode=0,
                stdout="device\n",
                stderr="",
            ),
            ("adb", "-s", "emulator-5554", "shell", "getprop", "sys.boot_completed"): CommandResult(
                argv=("adb", "-s", "emulator-5554", "shell", "getprop", "sys.boot_completed"),
                returncode=0,
                stdout="1\n",
                stderr="",
            ),
        }
        provider = AndroidEmulatorProvider(
            mode=DeviceMode.EXISTING_DEVICE,
            adb_serials=("emulator-5554",),
            command_runner=FakeCommandRunner(responses),
        )

        instances = provider.provision_instances(profile=self.profile, instance_count=None)

        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].instance_id, "emulator-5554")
        self.assertEqual(instances[0].avd_name, "Pixel_6_API_34")
        self.assertEqual(instances[0].console_port, 5554)
        self.assertEqual(instances[0].health_status.value, "HEALTHY")
        events = provider.events()
        self.assertTrue(any(event.event == "discovery" for event in events))
        self.assertTrue(any(event.event == "provisioned" for event in events))

    def test_managed_avd_mode_fails_fast_when_no_matching_running_avd_exists(self) -> None:
        responses = {
            ("adb", "devices", "-l"): CommandResult(
                argv=("adb", "devices", "-l"),
                returncode=0,
                stdout="List of devices attached\nemulator-5554 device transport_id:32\n",
                stderr="",
            ),
            ("adb", "-s", "emulator-5554", "shell", "getprop", "ro.boot.qemu.avd_name"): CommandResult(
                argv=("adb", "-s", "emulator-5554", "shell", "getprop", "ro.boot.qemu.avd_name"),
                returncode=0,
                stdout="Pixel_5_API_34\n",
                stderr="",
            ),
        }
        provider = AndroidEmulatorProvider(
            mode=DeviceMode.MANAGED_AVD,
            avd_names=("Pixel_6_API_34",),
            command_runner=FakeCommandRunner(responses),
        )

        with self.assertRaises(DeviceError) as context:
            provider.provision_instances(profile=self.profile, instance_count=1)

        self.assertIn("managed_avd mode", str(context.exception))

    def test_existing_device_provider_falls_back_when_first_avd_name_probe_times_out(self) -> None:
        responses = {
            ("adb", "devices", "-l"): CommandResult(
                argv=("adb", "devices", "-l"),
                returncode=0,
                stdout="List of devices attached\nemulator-5554 device transport_id:32\n",
                stderr="",
            ),
            ("adb", "-s", "emulator-5554", "shell", "getprop", "ro.boot.qemu.avd_name"): subprocess.TimeoutExpired(
                cmd=("adb", "-s", "emulator-5554", "shell", "getprop", "ro.boot.qemu.avd_name"),
                timeout=10,
            ),
            ("adb", "-s", "emulator-5554", "shell", "getprop", "persist.sys.avd_name"): CommandResult(
                argv=("adb", "-s", "emulator-5554", "shell", "getprop", "persist.sys.avd_name"),
                returncode=0,
                stdout="Pixel_6_API_34\n",
                stderr="",
            ),
            ("adb", "-s", "emulator-5554", "get-state"): CommandResult(
                argv=("adb", "-s", "emulator-5554", "get-state"),
                returncode=0,
                stdout="device\n",
                stderr="",
            ),
            ("adb", "-s", "emulator-5554", "shell", "getprop", "sys.boot_completed"): CommandResult(
                argv=("adb", "-s", "emulator-5554", "shell", "getprop", "sys.boot_completed"),
                returncode=0,
                stdout="1\n",
                stderr="",
            ),
        }
        provider = AndroidEmulatorProvider(
            mode=DeviceMode.EXISTING_DEVICE,
            adb_serials=("emulator-5554",),
            command_runner=FakeCommandRunner(responses),
        )

        instances = provider.provision_instances(profile=self.profile, instance_count=None)

        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].avd_name, "Pixel_6_API_34")

    def test_existing_device_provider_discovers_androidworld_grpc_port_from_running_emulator(self) -> None:
        responses = {
            ("adb", "devices", "-l"): CommandResult(
                argv=("adb", "devices", "-l"),
                returncode=0,
                stdout="List of devices attached\nemulator-5562 device transport_id:42\n",
                stderr="",
            ),
            ("adb", "-s", "emulator-5562", "shell", "getprop", "ro.boot.qemu.avd_name"): CommandResult(
                argv=("adb", "-s", "emulator-5562", "shell", "getprop", "ro.boot.qemu.avd_name"),
                returncode=0,
                stdout="AndroidWorldAvd2\n",
                stderr="",
            ),
            ("ps", "-axww", "-o", "pid=,command="): CommandResult(
                argv=("ps", "-axww", "-o", "pid=,command="),
                returncode=0,
                stdout=(
                    "123 /opt/android/emulator/emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554\n"
                    "124 /opt/android/emulator/emulator -avd AndroidWorldAvd2 -no-snapshot -grpc 8555\n"
                ),
                stderr="",
            ),
            ("adb", "-s", "emulator-5562", "get-state"): CommandResult(
                argv=("adb", "-s", "emulator-5562", "get-state"),
                returncode=0,
                stdout="device\n",
                stderr="",
            ),
            ("adb", "-s", "emulator-5562", "shell", "getprop", "sys.boot_completed"): CommandResult(
                argv=("adb", "-s", "emulator-5562", "shell", "getprop", "sys.boot_completed"),
                returncode=0,
                stdout="1\n",
                stderr="",
            ),
        }
        provider = AndroidEmulatorProvider(
            mode=DeviceMode.EXISTING_DEVICE,
            adb_serials=("emulator-5562",),
            command_runner=FakeCommandRunner(responses),
        )

        instances = provider.provision_instances(profile=self.profile, instance_count=None)

        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].adb_serial, "emulator-5562")
        self.assertEqual(instances[0].console_port, 5562)
        self.assertEqual(instances[0].grpc_port, 8555)

    def test_existing_device_provider_maps_grpc_ports_by_emulator_console_port(self) -> None:
        responses = {
            ("adb", "devices", "-l"): CommandResult(
                argv=("adb", "devices", "-l"),
                returncode=0,
                stdout=(
                    "List of devices attached\n"
                    "emulator-5554 device transport_id:32\n"
                    "emulator-5556 device transport_id:33\n"
                ),
                stderr="",
            ),
            ("adb", "-s", "emulator-5554", "shell", "getprop", "ro.boot.qemu.avd_name"): CommandResult(
                argv=("adb", "-s", "emulator-5554", "shell", "getprop", "ro.boot.qemu.avd_name"),
                returncode=0,
                stdout="AndroidWorldAvd\n",
                stderr="",
            ),
            ("adb", "-s", "emulator-5556", "shell", "getprop", "ro.boot.qemu.avd_name"): CommandResult(
                argv=("adb", "-s", "emulator-5556", "shell", "getprop", "ro.boot.qemu.avd_name"),
                returncode=0,
                stdout="AndroidWorldAvd\n",
                stderr="",
            ),
            ("ps", "-axww", "-o", "pid=,command="): CommandResult(
                argv=("ps", "-axww", "-o", "pid=,command="),
                returncode=0,
                stdout=(
                    "123 /opt/android/emulator/emulator -avd AndroidWorldAvd -port 5554 -no-snapshot -grpc 8554\n"
                    "124 /opt/android/emulator/emulator -avd AndroidWorldAvd -port 5556 -no-snapshot -grpc 8556\n"
                ),
                stderr="",
            ),
            ("adb", "-s", "emulator-5554", "get-state"): CommandResult(
                argv=("adb", "-s", "emulator-5554", "get-state"),
                returncode=0,
                stdout="device\n",
                stderr="",
            ),
            ("adb", "-s", "emulator-5554", "shell", "getprop", "sys.boot_completed"): CommandResult(
                argv=("adb", "-s", "emulator-5554", "shell", "getprop", "sys.boot_completed"),
                returncode=0,
                stdout="1\n",
                stderr="",
            ),
            ("adb", "-s", "emulator-5556", "get-state"): CommandResult(
                argv=("adb", "-s", "emulator-5556", "get-state"),
                returncode=0,
                stdout="device\n",
                stderr="",
            ),
            ("adb", "-s", "emulator-5556", "shell", "getprop", "sys.boot_completed"): CommandResult(
                argv=("adb", "-s", "emulator-5556", "shell", "getprop", "sys.boot_completed"),
                returncode=0,
                stdout="1\n",
                stderr="",
            ),
        }
        provider = AndroidEmulatorProvider(
            mode=DeviceMode.EXISTING_DEVICE,
            adb_serials=("emulator-5554", "emulator-5556"),
            command_runner=FakeCommandRunner(responses),
        )

        instances = provider.provision_instances(profile=self.profile, instance_count=None)

        grpc_ports_by_serial = {instance.adb_serial: instance.grpc_port for instance in instances}
        self.assertEqual(grpc_ports_by_serial["emulator-5554"], 8554)
        self.assertEqual(grpc_ports_by_serial["emulator-5556"], 8556)

    def test_health_check_degrades_instead_of_aborting_when_boot_probe_times_out(self) -> None:
        responses = {
            ("adb", "-s", "emulator-5554", "get-state"): CommandResult(
                argv=("adb", "-s", "emulator-5554", "get-state"),
                returncode=0,
                stdout="device\n",
                stderr="",
            ),
            ("adb", "-s", "emulator-5554", "shell", "getprop", "sys.boot_completed"): subprocess.TimeoutExpired(
                cmd=("adb", "-s", "emulator-5554", "shell", "getprop", "sys.boot_completed"),
                timeout=15,
            ),
        }
        provider = AndroidEmulatorProvider(
            mode=DeviceMode.EXISTING_DEVICE,
            adb_serials=("emulator-5554",),
            command_runner=FakeCommandRunner(responses),
        )
        instance = EmulatorInstance(
            instance_id="emulator-5554",
            adb_serial="emulator-5554",
            appium_port=4723,
            grpc_port=8554,
            avd_name="Pixel_6_API_34",
            snapshot_name="clean-base",
            profile_id="api34_base",
        )

        status = provider.health_check(instance)

        self.assertEqual(status.value, "DEGRADED")

    def test_reset_does_not_abort_when_snapshot_restore_times_out(self) -> None:
        responses = {
            ("adb", "-s", "emulator-5554", "emu", "avd", "snapshot", "load", "clean-base"): subprocess.TimeoutExpired(
                cmd=("adb", "-s", "emulator-5554", "emu", "avd", "snapshot", "load", "clean-base"),
                timeout=90,
            ),
        }
        provider = AndroidEmulatorProvider(
            mode=DeviceMode.EXISTING_DEVICE,
            adb_serials=("emulator-5554",),
            command_runner=FakeCommandRunner(responses),
        )
        instance = EmulatorInstance(
            instance_id="emulator-5554",
            adb_serial="emulator-5554",
            appium_port=4723,
            grpc_port=8554,
            avd_name="Pixel_6_API_34",
            snapshot_name="clean-base",
            profile_id="api34_base",
        )

        provider.reset(
            instance,
            policy_name="restore_snapshot_then_seed",
            benchmark_seed_requested=False,
        )

        self.assertTrue(any(event.event == "reset" for event in provider.events()))
