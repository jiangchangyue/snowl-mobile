from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from snowl_mobile.core.trial_spec import TrialSpec
from snowl_mobile.schemas.base import SchemaModel


@dataclass(frozen=True, slots=True)
class TrialContext(SchemaModel):
    trial_spec: TrialSpec
    emulator_instance_id: str | None = None
    emulator_adb_serial: str | None = None
    trial_output_dir: Path | None = None
