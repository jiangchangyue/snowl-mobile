from __future__ import annotations

import logging
import sys
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


class MobileAgentV35MobileSafetyBenchBridgeTestCase(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
