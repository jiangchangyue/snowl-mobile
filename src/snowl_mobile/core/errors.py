from __future__ import annotations


class SnowlMobileError(Exception):
    """Base exception for repository-defined errors."""


class ConfigError(SnowlMobileError):
    """Raised when project configuration cannot be loaded or validated."""

    def __init__(self, message: str, *, path: str | None = None) -> None:
        self.path = path
        rendered = f"{path}: {message}" if path else message
        super().__init__(rendered)


class RegistryError(SnowlMobileError):
    """Raised when a plugin registration or lookup fails."""


class ArtifactError(SnowlMobileError):
    """Raised when artifact scaffolding or persistence fails."""


class IntegrationError(SnowlMobileError):
    """Raised when local third-party repository inspection or scaffolding fails."""


class StateTransitionError(SnowlMobileError):
    """Raised when a trial status transition is invalid."""


class SchedulerError(SnowlMobileError):
    """Raised when scheduler operations fail."""


class DeviceError(SnowlMobileError):
    """Raised when emulator discovery, health checks, or reset hooks fail."""


class WorkerError(SnowlMobileError):
    """Raised when worker launch or execution fails."""


class WorkerTimeoutError(WorkerError):
    """Raised when a worker does not respond within its timeout budget."""


class WorkerCrashError(WorkerError):
    """Raised when a worker process crashes or exits unexpectedly."""


class WorkerProtocolError(WorkerError):
    """Raised when worker transport messages are malformed or invalid."""


class PhaseStubError(SnowlMobileError):
    """Raised when a later-phase placeholder is invoked too early."""
