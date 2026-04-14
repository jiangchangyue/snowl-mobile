from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from snowl_mobile.adapters.base import AdapterMetadata, BaseAdapter
from snowl_mobile.core.errors import RegistryError


AdapterFactory = Callable[[], BaseAdapter]


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    adapter_id: str
    kind: str
    factory: AdapterFactory
    metadata: AdapterMetadata


@dataclass(slots=True)
class Registry:
    agents: dict[str, RegistryEntry] = field(default_factory=dict)
    benchmarks: dict[str, RegistryEntry] = field(default_factory=dict)
    bridges: dict[str, RegistryEntry] = field(default_factory=dict)
    scorers: dict[str, RegistryEntry] = field(default_factory=dict)
    model_providers: dict[str, Any] = field(default_factory=dict)
    reset_strategies: dict[str, Any] = field(default_factory=dict)

    def register_agent(self, adapter_id: str, adapter: type[BaseAdapter] | BaseAdapter) -> None:
        self._register_adapter(self.agents, "agent", adapter_id, adapter)

    def register_benchmark(self, adapter_id: str, adapter: type[BaseAdapter] | BaseAdapter) -> None:
        self._register_adapter(self.benchmarks, "benchmark", adapter_id, adapter)

    def register_bridge(self, adapter_id: str, adapter: type[BaseAdapter] | BaseAdapter) -> None:
        self._register_adapter(self.bridges, "bridge", adapter_id, adapter)

    def register_scorer(self, adapter_id: str, adapter: type[BaseAdapter] | BaseAdapter) -> None:
        self._register_adapter(self.scorers, "scorer", adapter_id, adapter)

    def register_model_provider(self, name: str, provider: Any) -> None:
        self._register_plain(self.model_providers, name, provider)

    def register_reset_strategy(self, name: str, strategy: Any) -> None:
        self._register_plain(self.reset_strategies, name, strategy)

    def resolve_agent(self, adapter_id: str) -> RegistryEntry:
        return self._resolve(self.agents, adapter_id, "agent")

    def resolve_benchmark(self, adapter_id: str) -> RegistryEntry:
        return self._resolve(self.benchmarks, adapter_id, "benchmark")

    def resolve_bridge(self, adapter_id: str) -> RegistryEntry:
        return self._resolve(self.bridges, adapter_id, "bridge")

    def resolve_bridge_for_pair(self, agent_id: str, benchmark_id: str) -> RegistryEntry | None:
        for entry in self.list_by_kind("bridge"):
            if entry.metadata.extra.get("agent_id") != agent_id:
                continue
            if entry.metadata.extra.get("benchmark_id") != benchmark_id:
                continue
            return entry
        return None

    def resolve_scorer(self, adapter_id: str) -> RegistryEntry:
        return self._resolve(self.scorers, adapter_id, "scorer")

    def instantiate_agent(self, adapter_id: str) -> BaseAdapter:
        return self.resolve_agent(adapter_id).factory()

    def instantiate_benchmark(self, adapter_id: str) -> BaseAdapter:
        return self.resolve_benchmark(adapter_id).factory()

    def instantiate_bridge(self, adapter_id: str) -> BaseAdapter:
        return self.resolve_bridge(adapter_id).factory()

    def instantiate_scorer(self, adapter_id: str) -> BaseAdapter:
        return self.resolve_scorer(adapter_id).factory()

    def list_by_kind(self, kind: str) -> list[RegistryEntry]:
        bucket = self._bucket_for_kind(kind)
        return [bucket[key] for key in sorted(bucket)]

    def query(
        self,
        kind: str,
        *,
        integration_mode: str | None = None,
        modality: str | None = None,
        backend: str | None = None,
        requires_env: str | None = None,
    ) -> list[RegistryEntry]:
        entries = self.list_by_kind(kind)
        results: list[RegistryEntry] = []
        for entry in entries:
            metadata = entry.metadata
            if integration_mode and metadata.integration_mode != integration_mode:
                continue
            if modality and modality not in metadata.supported_modalities:
                continue
            if backend and backend not in metadata.supported_backends:
                continue
            if requires_env and requires_env not in metadata.required_env:
                continue
            results.append(entry)
        return results

    def summary(self) -> dict[str, list[str]]:
        return {
            "agents": sorted(self.agents),
            "benchmarks": sorted(self.benchmarks),
            "bridges": sorted(self.bridges),
            "scorers": sorted(self.scorers),
            "model_providers": sorted(self.model_providers),
            "reset_strategies": sorted(self.reset_strategies),
        }

    def metadata_summary(self) -> dict[str, list[dict[str, object]]]:
        return {
            kind: [asdict(entry.metadata) for entry in self.list_by_kind(kind)]
            for kind in ("agent", "benchmark", "bridge", "scorer")
        }

    def _register_adapter(
        self,
        bucket: dict[str, RegistryEntry],
        expected_kind: str,
        adapter_id: str,
        adapter: type[BaseAdapter] | BaseAdapter,
    ) -> None:
        if adapter_id in bucket:
            raise RegistryError(f"duplicate {expected_kind} registration for '{adapter_id}'")

        factory = self._build_factory(adapter)
        instance = factory()
        metadata = instance.metadata()
        if metadata.kind != expected_kind:
            raise RegistryError(
                f"adapter '{adapter_id}' reported kind '{metadata.kind}', expected '{expected_kind}'"
            )
        if metadata.adapter_id != adapter_id:
            raise RegistryError(
                f"adapter '{adapter_id}' reported adapter_id '{metadata.adapter_id}'"
            )

        bucket[adapter_id] = RegistryEntry(
            adapter_id=adapter_id,
            kind=expected_kind,
            factory=factory,
            metadata=metadata,
        )

    def _build_factory(self, adapter: type[BaseAdapter] | BaseAdapter) -> AdapterFactory:
        if isinstance(adapter, BaseAdapter):
            adapter_cls = adapter.__class__
            return lambda: adapter_cls()
        if isinstance(adapter, type) and issubclass(adapter, BaseAdapter):
            return adapter
        raise RegistryError("adapter registrations must use BaseAdapter subclasses or instances")

    def _register_plain(self, bucket: dict[str, Any], name: str, value: Any) -> None:
        if name in bucket:
            raise RegistryError(f"duplicate registration for '{name}'")
        bucket[name] = value

    def _resolve(self, bucket: dict[str, RegistryEntry], adapter_id: str, kind: str) -> RegistryEntry:
        try:
            return bucket[adapter_id]
        except KeyError as error:
            raise RegistryError(f"unregistered {kind} adapter '{adapter_id}'") from error

    def _bucket_for_kind(self, kind: str) -> dict[str, RegistryEntry]:
        buckets = {
            "agent": self.agents,
            "benchmark": self.benchmarks,
            "bridge": self.bridges,
            "scorer": self.scorers,
        }
        try:
            return buckets[kind]
        except KeyError as error:
            allowed = ", ".join(sorted(buckets))
            raise RegistryError(f"unknown registry kind '{kind}' (allowed: {allowed})") from error
