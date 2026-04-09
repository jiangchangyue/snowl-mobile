from __future__ import annotations

from typing import Any, Iterable

from snowl_mobile.core.errors import ConfigError


def expect_mapping(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError("expected a mapping", path=path)
    return value


def expect_list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ConfigError("expected a list", path=path)
    return value


def get_required(
    data: dict[str, Any],
    key: str,
    path: str,
    *,
    aliases: tuple[str, ...] = (),
) -> object:
    for candidate in (key, *aliases):
        if candidate in data:
            return data[candidate]
    raise ConfigError(f"missing required field '{key}'", path=path)


def get_optional(
    data: dict[str, Any],
    key: str,
    default: object,
    *,
    aliases: tuple[str, ...] = (),
) -> object:
    for candidate in (key, *aliases):
        if candidate in data:
            return data[candidate]
    return default


def expect_string(value: object, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ConfigError("expected a string", path=path)
    normalized = value.strip()
    if not allow_empty and not normalized:
        raise ConfigError("must not be empty", path=path)
    return normalized


def expect_bool(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError("expected a boolean", path=path)
    return value


def expect_int(value: object, path: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError("expected an integer", path=path)
    if minimum is not None and value < minimum:
        raise ConfigError(f"must be >= {minimum}", path=path)
    return value


def expect_string_list(
    value: object,
    path: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    items = expect_list(value, path)
    normalized: list[str] = []
    for index, item in enumerate(items):
        normalized.append(expect_string(item, f"{path}[{index}]"))
    if not allow_empty and not normalized:
        raise ConfigError("must not be empty", path=path)
    return tuple(normalized)


def expect_mapping_of_strings(value: object, path: str) -> dict[str, str]:
    mapping = expect_mapping(value, path)
    normalized: dict[str, str] = {}
    for key, item in mapping.items():
        normalized[expect_string(key, f"{path}.<key>")] = expect_string(
            item, f"{path}.{key}", allow_empty=True
        )
    return normalized


def ensure_unique(values: Iterable[str], path: str, label: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        raise ConfigError(f"duplicate {label}: {duplicate_list}", path=path)


def expect_enum_member(value: object, path: str, enum_cls: type) -> object:
    raw = expect_string(value, path)
    try:
        return enum_cls(raw)
    except ValueError as error:
        allowed = ", ".join(member.value for member in enum_cls)
        raise ConfigError(f"unsupported value '{raw}' (allowed: {allowed})", path=path) from error
