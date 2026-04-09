from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from snowl_mobile.schemas.base import SchemaModel


@dataclass(frozen=True, slots=True)
class ObservationBundle(SchemaModel):
    timestamp: str | None = None
    screenshot_path: str | None = None
    xml_path: str | None = None
    ui_tree_json_path: str | None = None
    parsed_text: str | None = None
    activity: str | None = None
    package_name: str | None = None
    screen_size: str | None = None
    orientation: str | None = None
    source_backend: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
