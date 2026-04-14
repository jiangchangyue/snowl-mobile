from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from snowl_mobile.core.enums import IntegrationMode


@dataclass(frozen=True, slots=True)
class AdapterMetadata:
    adapter_id: str
    kind: str
    integration_mode: str
    supported_modalities: tuple[str, ...] = ()
    supported_backends: tuple[str, ...] = ()
    required_env: tuple[str, ...] = ()
    supported_model_protocols: tuple[str, ...] = ()
    supported_benchmarks: tuple[str, ...] = ()
    extra: dict[str, object] = field(default_factory=dict)


class BaseAdapter(ABC):
    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Stable adapter identifier used by the registry."""

    @property
    @abstractmethod
    def kind(self) -> str:
        """Registry bucket name, e.g. agent or benchmark."""

    @abstractmethod
    def metadata(self) -> AdapterMetadata:
        """Return registry-facing metadata for discovery and compatibility checks."""

    @property
    def integration_mode(self) -> IntegrationMode:
        return IntegrationMode(self.metadata().integration_mode)
