from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from snowl_mobile.core.errors import ConfigError


@dataclass(frozen=True, slots=True)
class _Line:
    indent: int
    content: str
    number: int


def parse_yaml_text(text: str) -> Any:
    """Parse a small YAML subset used by Phase 0 configs.

    Supported forms:
    - indentation-based mappings
    - sequences introduced with `-`
    - inline lists like `[a, b]`
    - booleans, ints, floats, null, and unquoted strings
    """

    lines = _prepare_lines(text)
    if not lines:
        return {}

    value, index = _parse_block(lines, 0, lines[0].indent)
    if index != len(lines):
        extra = lines[index]
        raise ConfigError(f"unexpected trailing content at line {extra.number}")
    return value


def _prepare_lines(text: str) -> list[_Line]:
    prepared: list[_Line] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        prepared.append(_Line(indent=indent, content=raw[indent:], number=number))
    return prepared


def _parse_block(lines: list[_Line], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    line = lines[index]
    if line.indent != indent:
        raise ConfigError(f"unexpected indentation at line {line.number}")
    if line.content.startswith("- "):
        return _parse_sequence(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def _parse_mapping(lines: list[_Line], index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent > indent:
            raise ConfigError(f"unexpected indentation at line {line.number}")
        if line.content.startswith("- "):
            break

        key, value_text = _split_mapping_entry(line)
        if value_text == "":
            index += 1
            if index >= len(lines) or lines[index].indent <= indent:
                result[key] = None
                continue
            nested, index = _parse_block(lines, index, lines[index].indent)
            result[key] = nested
            continue

        result[key] = _parse_scalar(value_text)
        index += 1
    return result, index


def _parse_sequence(lines: list[_Line], index: int, indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent != indent or not line.content.startswith("- "):
            break

        payload = line.content[2:].strip()
        if not payload:
            index += 1
            if index >= len(lines) or lines[index].indent <= indent:
                items.append(None)
                continue
            nested, index = _parse_block(lines, index, lines[index].indent)
            items.append(nested)
            continue

        if _looks_like_mapping_entry(payload):
            item_lines = [_Line(indent=indent + 2, content=payload, number=line.number)]
            next_index = index + 1
            while next_index < len(lines) and lines[next_index].indent > indent:
                item_lines.append(lines[next_index])
                next_index += 1
            item, consumed = _parse_mapping(item_lines, 0, indent + 2)
            if consumed != len(item_lines):
                extra = item_lines[consumed]
                raise ConfigError(f"unexpected sequence item content at line {extra.number}")
            items.append(item)
            index = next_index
            continue

        items.append(_parse_scalar(payload))
        index += 1
    return items, index


def _split_mapping_entry(line: _Line) -> tuple[str, str]:
    if ":" not in line.content:
        raise ConfigError(f"expected mapping entry at line {line.number}")
    key, value = line.content.split(":", 1)
    key = key.strip()
    if not key:
        raise ConfigError(f"empty mapping key at line {line.number}")
    return key, value.strip()


def _looks_like_mapping_entry(payload: str) -> bool:
    if ":" not in payload:
        return False
    key, _value = payload.split(":", 1)
    return bool(key.strip())


def _parse_scalar(value: str) -> Any:
    if value == "{}":
        return {}
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in inner.split(",")]

    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]

    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        pass

    return value
