from __future__ import annotations

from typing import Protocol


class RuntimeBridge(Protocol):
    def create_session(self) -> None:
        ...

    def cleanup(self) -> None:
        ...
