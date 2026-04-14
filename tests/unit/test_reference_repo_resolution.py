from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.adapters.agents.mobile_agent_e import resolve_mobile_agent_e_repo_path
from snowl_mobile.adapters.agents.mobile_agent_v3_5 import resolve_mobile_agent_v3_5_repo_path
from snowl_mobile.adapters.agents.open_autoglm import resolve_open_autoglm_repo_path
from snowl_mobile.adapters.benchmarks.androidworld import resolve_androidworld_repo_path
from snowl_mobile.adapters.benchmarks.mobilesafetybench import resolve_mobilesafetybench_repo_path
from snowl_mobile.adapters.benchmarks import mobilesafetybench as mobilesafetybench_module
from snowl_mobile.cli.main import _apply_platform_env_defaults
from snowl_mobile.core.errors import IntegrationError


class ReferenceRepoResolutionTestCase(unittest.TestCase):
    def test_resolvers_ignore_exported_home_vars_and_use_local_references(self) -> None:
        stale_root = "/tmp/snowl-mobile-stale-home"
        with mock.patch.dict(
            os.environ,
            {
                "OPEN_AUTOGLM_HOME": stale_root,
                "MOBILE_AGENT_E_HOME": stale_root,
                "MOBILE_AGENT_V3_5_HOME": stale_root,
                "MOBILE_SAFETY_HOME": stale_root,
                "ANDROID_WORLD_HOME": stale_root,
            },
            clear=False,
        ):
            self.assertEqual(
                resolve_open_autoglm_repo_path(),
                ROOT / "references" / "agents" / "Open-AutoGLM",
            )
            self.assertEqual(
                resolve_mobile_agent_e_repo_path(),
                ROOT / "references" / "agents" / "MobileAgent" / "Mobile-Agent-E",
            )
            self.assertEqual(
                resolve_mobile_agent_v3_5_repo_path(),
                ROOT / "references" / "agents" / "MobileAgent" / "Mobile-Agent-v3.5",
            )
            self.assertEqual(
                resolve_mobilesafetybench_repo_path(),
                ROOT / "references" / "benchmarks" / "mobilesafetybench",
            )
            self.assertEqual(
                resolve_androidworld_repo_path(),
                ROOT / "references" / "benchmarks" / "android_world",
            )

    def test_apply_platform_env_defaults_overwrites_stale_repo_homes(self) -> None:
        stale_root = "/tmp/snowl-mobile-stale-home"
        with mock.patch.dict(
            os.environ,
            {
                "OPEN_AUTOGLM_HOME": stale_root,
                "MOBILE_AGENT_E_HOME": stale_root,
                "MOBILE_AGENT_V3_5_HOME": stale_root,
                "MOBILE_SAFETY_HOME": stale_root,
                "ANDROID_WORLD_HOME": stale_root,
            },
            clear=False,
        ):
            _apply_platform_env_defaults()

            self.assertEqual(
                os.environ["OPEN_AUTOGLM_HOME"],
                str(ROOT / "references" / "agents" / "Open-AutoGLM"),
            )
            self.assertEqual(
                os.environ["MOBILE_AGENT_E_HOME"],
                str(ROOT / "references" / "agents" / "MobileAgent" / "Mobile-Agent-E"),
            )
            self.assertEqual(
                os.environ["MOBILE_AGENT_V3_5_HOME"],
                str(ROOT / "references" / "agents" / "MobileAgent" / "Mobile-Agent-v3.5"),
            )
            self.assertEqual(
                os.environ["MOBILE_SAFETY_HOME"],
                str(ROOT / "references" / "benchmarks" / "mobilesafetybench"),
            )
            self.assertEqual(
                os.environ["ANDROID_WORLD_HOME"],
                str(ROOT / "references" / "benchmarks" / "android_world"),
            )

    def test_missing_reference_repo_error_tells_user_to_clone_under_references(self) -> None:
        with mock.patch.object(
            mobilesafetybench_module,
            "_DEFAULT_REPO_CANDIDATES",
            (Path("references/benchmarks/mobilesafetybench_missing_for_test"),),
        ):
            with self.assertRaises(IntegrationError) as context:
                resolve_mobilesafetybench_repo_path(Path("/tmp/external-mobile-safety"))

        message = str(context.exception)
        self.assertIn("under references/", message)
        self.assertIn("Please clone the upstream repository", message)
        self.assertIn("references/benchmarks/mobilesafetybench_missing_for_test", message)
        self.assertIn("Ignored external path '/tmp/external-mobile-safety'", message)
