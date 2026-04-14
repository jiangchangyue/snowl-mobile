from __future__ import annotations

from typing import Protocol


class ModelClient(Protocol):
    def invoke(self, request: object) -> object:
        """Later phases should provide concrete request and response models."""
