from __future__ import annotations

import logging
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.adapters.bridges.mobile_agent_v3_5_mobilesafetybench import (
    MobileAgentV35MobileSafetyBenchBridgeAdapter,
)
from snowl_mobile.schemas.observation import ObservationBundle


class MobileAgentV35MobileSafetyBenchBridgeTestCase(unittest.TestCase):
    def test_bridge_replays_terminal_benchmark_action_for_finish_signal(self) -> None:
        bridge = MobileAgentV35MobileSafetyBenchBridgeAdapter()
        final_timestep = SimpleNamespace(
            progress={
                "finished": False,
                "goal achievement": False,
                "harm prevention": False,
                "risk-detected step": -1,
                "step": 1,
            },
            curr_obs={"text": "Messages inbox"},
        )

        class FakeEvaluator:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def evaluate(self, *, action: object, observation: object, driver: object) -> tuple[dict[str, object], tuple[bool, bool]]:
                self.calls.append(
                    {
                        "action": action,
                        "observation": observation,
                        "driver": driver,
                    }
                )
                return (
                    {
                        "finished": True,
                        "goal achievement": False,
                        "harm prevention": True,
                        "risk-detected step": 0,
                        "step": 2,
                    },
                    (False, True),
                )

        evaluator = FakeEvaluator()
        agent_result = SimpleNamespace(
            action_record=SimpleNamespace(
                executed_action={
                    "normalized_action": "finish",
                    "finish_flag": "success",
                }
            )
        )

        reconciled_progress, notes = bridge._reconcile_final_progress_with_terminal_action(  # noqa: SLF001
            env=SimpleNamespace(evaluator=evaluator, driver=object()),
            final_timestep=final_timestep,
            agent_result=agent_result,
            trial_logger=logging.getLogger("test.mobile_agent_v3_5_msb"),
        )

        self.assertEqual(evaluator.calls[0]["action"], "complete()")
        self.assertTrue(reconciled_progress["finished"])
        self.assertTrue(reconciled_progress["harm prevention"])
        self.assertIn("replayed the final MobileSafetyBench evaluator step", " ".join(notes))

    def test_bridge_keeps_unfinished_when_only_agent_reports_stop(self) -> None:
        bridge = MobileAgentV35MobileSafetyBenchBridgeAdapter()
        task = SimpleNamespace(
            task_id="high_risk_001",
            task_category="text_message_sending",
            risk_level="high_risk",
            evaluation={"goal_achievement_criteria": {"parameters": {}}},
        )
        agent_result = SimpleNamespace(
            platform_metrics={"finished": True, "finish_flag": "success"},
            native_metrics={"harm_prevention": True},
            trajectory_steps=(object(), object(), object(), object()),
        )

        native_metrics, notes = bridge._build_bridge_native_metrics(  # noqa: SLF001
            task=task,
            final_progress={
                "finished": False,
                "goal achievement": False,
                "harm prevention": False,
                "risk-detected step": 0,
                "step": 1,
            },
            final_xml_content="<hierarchy></hierarchy>\n",
            agent_result=agent_result,
        )

        self.assertFalse(native_metrics["finished"])
        self.assertFalse(native_metrics["harm_prevention"])
        self.assertEqual(native_metrics["step_count"], 4)
        self.assertIn("did not mark the task finished", " ".join(notes))
        self.assertIn("kept benchmark-native harm_prevention=false", " ".join(notes))

    def test_bridge_preserves_finished_when_benchmark_marks_completion(self) -> None:
        bridge = MobileAgentV35MobileSafetyBenchBridgeAdapter()
        task = SimpleNamespace(
            task_id="high_risk_001",
            task_category="text_message_sending",
            risk_level="high_risk",
            evaluation={"goal_achievement_criteria": {"parameters": {}}},
        )
        agent_result = SimpleNamespace(
            platform_metrics={"finished": True, "finish_flag": "success"},
            native_metrics={"harm_prevention": True},
            trajectory_steps=(object(), object(), object(), object()),
        )

        native_metrics, notes = bridge._build_bridge_native_metrics(  # noqa: SLF001
            task=task,
            final_progress={
                "finished": True,
                "goal achievement": False,
                "harm prevention": True,
                "risk-detected step": 0,
                "step": 4,
            },
            final_xml_content="<hierarchy></hierarchy>\n",
            agent_result=agent_result,
        )

        self.assertTrue(native_metrics["finished"])
        self.assertTrue(native_metrics["harm_prevention"])
        self.assertEqual(native_metrics["step_count"], 4)
        self.assertEqual(notes, ())

    def test_bridge_retries_final_state_after_recoverable_uiautomator2_crash(self) -> None:
        bridge = MobileAgentV35MobileSafetyBenchBridgeAdapter()
        calls = {"count": 0}

        class FakeEnv:
            def get_state(self, *, reset: bool = False) -> str:
                del reset
                calls["count"] += 1
                if calls["count"] == 1:
                    raise RuntimeError(
                        "GET /source cannot be proxied to UiAutomator2 server because the instrumentation process is not running"
                    )
                return "final-timestep"

        with mock.patch.object(
            bridge,
            "_recover_existing_device_driver",
        ) as recover_mock:
            result = bridge._get_state_with_existing_device_recovery(  # noqa: SLF001
                env=FakeEnv(),
                adb_serial="emulator-5554",
                trial_logger=logging.getLogger("test.mobile_agent_v3_5_msb"),
                state_label="Final environment state capture",
            )

        self.assertEqual(result, "final-timestep")
        self.assertEqual(calls["count"], 2)
        recover_mock.assert_called_once()

    def test_bridge_retries_final_state_after_invalid_session_id(self) -> None:
        bridge = MobileAgentV35MobileSafetyBenchBridgeAdapter()
        calls = {"count": 0}

        class FakeEnv:
            def get_state(self, *, reset: bool = False) -> str:
                del reset
                calls["count"] += 1
                if calls["count"] == 1:
                    raise RuntimeError(
                        "InvalidSessionIdException: The session identified by "
                        "e5b65d7a-fb6c-4cf5-8a26-3495fb5d3ac2 is not known"
                    )
                return "final-timestep"

        with mock.patch.object(
            bridge,
            "_recover_existing_device_driver",
        ) as recover_mock:
            result = bridge._get_state_with_existing_device_recovery(  # noqa: SLF001
                env=FakeEnv(),
                adb_serial="emulator-5554",
                trial_logger=logging.getLogger("test.mobile_agent_v3_5_msb"),
                state_label="Final environment state capture",
            )

        self.assertEqual(result, "final-timestep")
        self.assertEqual(calls["count"], 2)
        recover_mock.assert_called_once()

    def test_bridge_embeds_live_observation_paths_into_bootstrap_observation(self) -> None:
        bridge = MobileAgentV35MobileSafetyBenchBridgeAdapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "run"
            bridge_raw_dir = output_dir / "raw" / "mobile_agent_v3_5_mobilesafetybench"
            bridge_raw_dir.mkdir(parents=True, exist_ok=True)
            observation = ObservationBundle(
                timestamp="2026-04-16T00:00:00+00:00",
                screenshot_path="raw/mobile_agent_v3_5_mobilesafetybench/bootstrap.png",
                xml_path="raw/mobile_agent_v3_5_mobilesafetybench/bootstrap.xml",
                parsed_text="Messages home",
                source_backend="mobilesafetybench_real",
                extra={"task_category": "text_message_sending"},
            )

            updated = bridge._with_live_observation_paths(  # noqa: SLF001
                observation=observation,
                output_dir=output_dir,
                live_xml_path=bridge_raw_dir / "live_observation" / "latest.xml",
                live_screenshot_path=bridge_raw_dir / "live_observation" / "latest.png",
                live_observation_path=bridge_raw_dir / "live_observation" / "latest_observation.json",
            )

        self.assertEqual(updated.extra["bridge_live_observation_source"], "mobilesafetybench_curr_obs_sidecar")
        self.assertTrue(str(updated.extra["bridge_live_xml_path"]).endswith("live_observation/latest.xml"))
        self.assertTrue(str(updated.extra["bridge_live_screenshot_path"]).endswith("live_observation/latest.png"))
        self.assertTrue(
            str(updated.extra["bridge_live_observation_path"]).endswith("live_observation/latest_observation.json")
        )

    def test_bridge_live_observation_snapshot_keeps_png_suffix_for_temp_file(self) -> None:
        bridge = MobileAgentV35MobileSafetyBenchBridgeAdapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir) / "live_observation"
            observation = ObservationBundle(
                timestamp="2026-04-16T00:00:00+00:00",
                screenshot_path="raw/mobile_agent_v3_5_mobilesafetybench/bootstrap.png",
                xml_path="raw/mobile_agent_v3_5_mobilesafetybench/bootstrap.xml",
                parsed_text="Messages home",
                source_backend="mobilesafetybench_real",
            )

            observed_targets: list[Path] = []

            def _fake_write_png(target: Path, pixel_array: object) -> None:
                del pixel_array
                observed_targets.append(target)
                target.write_bytes(b"png")

            with mock.patch.object(
                bridge,
                "_write_png_from_observation_extra",
                side_effect=_fake_write_png,
            ) as write_png_mock:
                bridge._write_live_observation_snapshot(  # noqa: SLF001
                    xml_path=base / "latest.xml",
                    screenshot_path=base / "latest.png",
                    observation_path=base / "latest_observation.json",
                    observation=observation,
                    xml_content="<hierarchy></hierarchy>\n",
                    pixel_array=object(),
                    sequence=1,
                )

            write_png_mock.assert_called_once()
            self.assertEqual(observed_targets[0].name, "latest.tmp.png")
            self.assertEqual(observed_targets[0].suffix, ".png")
            self.assertFalse((base / "latest.tmp.png").exists())
            self.assertTrue((base / "latest.png").exists())


if __name__ == "__main__":
    unittest.main()
