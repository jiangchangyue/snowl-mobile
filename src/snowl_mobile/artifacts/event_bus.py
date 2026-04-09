from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from snowl_mobile.core.errors import ArtifactError


class EventBus:
    def __init__(self, path: Path) -> None:
        self.path = path

    def write_event(self, event: dict[str, Any]) -> None:
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=True) + "\n")
        except OSError as error:
            raise ArtifactError(f"failed to append event to {self.path}") from error
