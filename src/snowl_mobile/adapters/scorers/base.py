from __future__ import annotations

from abc import ABC, abstractmethod

from snowl_mobile.adapters.base import AdapterMetadata, BaseAdapter


class BaseScorerAdapter(BaseAdapter, ABC):
    kind = "scorer"

    @property
    @abstractmethod
    def benchmark_ids(self) -> tuple[str, ...]:
        """Benchmarks this scorer can evaluate."""

    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id=self.adapter_id,
            kind=self.kind,
            integration_mode="native",
            supported_benchmarks=self.benchmark_ids,
        )

    @abstractmethod
    def score(self, trial_artifacts: object) -> object:
        """Score a completed trial artifact bundle."""
