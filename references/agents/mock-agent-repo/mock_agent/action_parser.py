from __future__ import annotations


def parse_action(raw_output: str) -> dict[str, object]:
    return {"type": "tap", "selector": raw_output, "format": "json_action"}
