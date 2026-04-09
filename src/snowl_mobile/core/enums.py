from __future__ import annotations

from enum import StrEnum


class IntegrationMode(StrEnum):
    WRAP = "wrap"
    NATIVE = "native"
    HYBRID = "hybrid"


class ArtifactLevel(StrEnum):
    LIGHT = "light"
    STANDARD = "standard"
    FULL = "full"


class ObservationMode(StrEnum):
    TEXT_ONLY = "text_only"
    IMAGE_ONLY = "image_only"
    IMAGE_TEXT = "image_text"
    BENCHMARK_NATIVE = "benchmark_native"


class WorkerMode(StrEnum):
    IN_PROCESS = "in_process"
    VENV = "venv"
    CONTAINER = "container"


class EnvironmentIsolation(StrEnum):
    HOST = "host"
    PER_WORKER_VENV = "per_worker_venv"
    CONTAINER = "container"


class DeviceMode(StrEnum):
    FAKE = "fake"
    EXISTING_DEVICE = "existing_device"
    MANAGED_AVD = "managed_avd"


class ResetScope(StrEnum):
    RUN = "run"
    TRIAL = "trial"


class TaskSourceKind(StrEnum):
    INLINE = "inline"
    LOCAL_PATH = "local_path"
    REFERENCE_REPO = "reference_repo"
    GENERATED_PACKAGE = "generated_package"
