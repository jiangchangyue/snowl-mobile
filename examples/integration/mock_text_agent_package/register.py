from __future__ import annotations

from snowl_mobile.core.registry import Registry

from .adapter import MockTextAgentAdapter


def register_mock_text_agent(registry: Registry) -> None:
    """TODO: call this from the chosen registry bootstrap location."""
    registry.register_agent("mock_text_agent", MockTextAgentAdapter)
