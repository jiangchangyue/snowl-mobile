from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from snowl_mobile.core.errors import ConfigError


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}")


def autoload_local_env_files(cwd: Path | None = None) -> tuple[Path, ...]:
    base = cwd or Path.cwd()
    loaded: list[Path] = []
    for candidate in (base / ".env", base / ".env.local"):
        if candidate.exists():
            load_env_file(candidate, override=True)
            loaded.append(candidate)
    return tuple(loaded)


def load_env_file(path: Path, *, override: bool = True) -> dict[str, str]:
    loaded: dict[str, str] = {}
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"failed to read env file: {path}") from error

    for number, raw in enumerate(content.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        if "=" not in stripped:
            raise ConfigError(f"invalid env entry at {path}:{number}")
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            raise ConfigError(f"empty env key at {path}:{number}")
        value = _strip_env_quotes(value.strip())
        if override or key not in os.environ:
            os.environ[key] = value
        loaded[key] = value
    return loaded


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


def _strip_env_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
