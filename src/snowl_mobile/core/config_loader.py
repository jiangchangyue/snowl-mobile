from __future__ import annotations

from pathlib import Path
from typing import Any

from snowl_mobile.core.errors import ConfigError
from snowl_mobile.core.project_spec import ProjectSpec
from snowl_mobile.utils.simple_yaml import parse_yaml_text
from snowl_mobile.utils.envfiles import expand_env_placeholders


def load_project_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"project config does not exist: {path}")

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"failed to read project config: {path}") from error

    data = parse_yaml_text(content)
    if not isinstance(data, dict):
        raise ConfigError("top-level project config must be a mapping")
    expanded = expand_env_placeholders(data)
    if not isinstance(expanded, dict):
        raise ConfigError("top-level project config must be a mapping")
    return expanded


def load_project_spec(path: Path) -> ProjectSpec:
    return ProjectSpec.from_mapping(load_project_mapping(path))
