from __future__ import annotations

from snowl_mobile.core.registry import Registry

from .bridge import DummyVisionDummyBenchmarkBridgeAdapter


def register_dummy_vision__dummy_benchmark(registry: Registry) -> None:
    """TODO: call this from the chosen registry bootstrap location."""
    registry.register_bridge("dummy_vision__dummy_benchmark", DummyVisionDummyBenchmarkBridgeAdapter)
