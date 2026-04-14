from __future__ import annotations

from dataclasses import asdict
from typing import Any


class SchemaModel:
    """Small dataclass mixin for stable dict snapshots."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
