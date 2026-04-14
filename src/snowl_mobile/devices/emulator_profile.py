from __future__ import annotations

from dataclasses import dataclass

from snowl_mobile.core.validation import expect_int, expect_string, expect_string_list, get_optional, get_required
from snowl_mobile.schemas.base import SchemaModel


@dataclass(frozen=True, slots=True)
class EmulatorProfile(SchemaModel):
    profile_id: str
    base_avd_name: str
    platform: str
    api_level: int
    system_image: str
    snapshot_name: str
    screen_size: str
    grpc_port: int
    tags: tuple[str, ...]

    @classmethod
    def from_mapping(cls, data: dict[str, object], path: str) -> "EmulatorProfile":
        return cls(
            profile_id=expect_string(
                get_required(data, "profile_id", path, aliases=("id",)),
                f"{path}.profile_id",
            ),
            base_avd_name=expect_string(
                get_required(data, "base_avd_name", path),
                f"{path}.base_avd_name",
            ),
            platform=expect_string(get_optional(data, "platform", "android"), f"{path}.platform"),
            api_level=expect_int(get_required(data, "api_level", path), f"{path}.api_level", minimum=1),
            system_image=expect_string(
                get_required(data, "system_image", path),
                f"{path}.system_image",
            ),
            snapshot_name=expect_string(
                get_required(data, "snapshot_name", path),
                f"{path}.snapshot_name",
            ),
            screen_size=expect_string(
                get_optional(data, "screen_size", "unknown"),
                f"{path}.screen_size",
            ),
            grpc_port=expect_int(
                get_optional(data, "grpc_port", 8554),
                f"{path}.grpc_port",
                minimum=1,
            ),
            tags=expect_string_list(get_optional(data, "tags", []), f"{path}.tags"),
        )
