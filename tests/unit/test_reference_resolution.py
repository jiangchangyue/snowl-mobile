from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.integration import references as references_module


class ReferenceResolutionTestCase(unittest.TestCase):
    def _make_project_root(self, root: Path) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        (root / "pyproject.toml").write_text("[project]\nname = 'snowl-mobile'\n", encoding="utf-8")
        (root / "src" / "snowl_mobile").mkdir(parents=True, exist_ok=True)
        (root / "references").mkdir(parents=True, exist_ok=True)
        return root

    def test_repository_root_prefers_current_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = self._make_project_root(Path(temp_dir) / "workspace")
            nested_dir = project_root / "results" / "latest"
            nested_dir.mkdir(parents=True, exist_ok=True)

            with mock.patch.object(references_module.Path, "cwd", return_value=nested_dir):
                resolved = references_module.repository_root()
                candidate = references_module.normalize_reference_candidate(
                    Path("references/agents/Open-AutoGLM")
                )

        self.assertEqual(resolved.resolve(), project_root.resolve())
        self.assertEqual(
            candidate.resolve(),
            (project_root / "references" / "agents" / "Open-AutoGLM").resolve(),
        )

    def test_repository_root_prefers_env_override_over_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = self._make_project_root(Path(temp_dir) / "workspace")

            with (
                mock.patch.dict(
                    os.environ,
                    {references_module._PROJECT_ROOT_ENV_VAR: str(project_root)},
                    clear=False,
                ),
                mock.patch.object(references_module.Path, "cwd", return_value=Path("/tmp")),
            ):
                resolved = references_module.repository_root()

        self.assertEqual(resolved.resolve(), project_root.resolve())

    def test_repository_root_falls_back_to_package_checkout(self) -> None:
        with mock.patch.object(references_module.Path, "cwd", return_value=Path("/tmp")):
            resolved = references_module.repository_root()

        self.assertEqual(resolved, ROOT)


if __name__ == "__main__":
    unittest.main()
