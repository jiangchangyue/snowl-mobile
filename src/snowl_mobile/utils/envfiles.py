from __future__ import annotations

import os
import re
from typing import Any

from snowl_mobile.core.errors import ConfigError


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}")


def expand_env_placeholders(value: Any, *, path: str = "config") -> Any:
    if isinstance(value, dict):
        return {
            key: expand_env_placeholders(item, path=f"{path}.{key}")
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            expand_env_placeholders(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda match: _replace_env_match(match, path=path), value)
    return value


def _replace_env_match(match: re.Match[str], *, path: str) -> str:
    key = match.group(1)
    default = match.group(3)
    resolved = os.environ.get(key, default)
    if resolved is None:
        raise ConfigError(
            f"environment variable '{key}' is required to expand this config value",
            path=path,
        )
    return resolved
