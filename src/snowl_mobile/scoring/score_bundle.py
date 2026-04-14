from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from snowl_mobile.schemas.base import SchemaModel


@dataclass(frozen=True, slots=True)
class ScoreBundle(SchemaModel):
    native_metrics: dict[str, Any] = field(default_factory=dict)
    primary_metric: Any = None
    platform_metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
