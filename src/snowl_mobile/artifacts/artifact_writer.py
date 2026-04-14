from __future__ import annotations

from pathlib import Path

from snowl_mobile.artifacts.store import ArtifactStore
from snowl_mobile.artifacts.paths import RunLayout
from snowl_mobile.core.project_spec import ProjectSpec


class ArtifactWriter(ArtifactStore):
    """Backward-compatible wrapper kept for earlier phase imports."""

    def create_run_scaffold(self, spec: ProjectSpec, project_source: Path) -> RunLayout:
        return super().create_run_scaffold(spec=spec, project_source=project_source)
