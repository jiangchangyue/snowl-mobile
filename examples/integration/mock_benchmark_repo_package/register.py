from __future__ import annotations

from snowl_mobile.core.registry import Registry

from .adapter import MockBenchmarkRepoAdapter


def register_mock_benchmark_repo(registry: Registry) -> None:
    """TODO: call this from the chosen registry bootstrap location."""
    registry.register_benchmark("mock_benchmark_repo", MockBenchmarkRepoAdapter)
