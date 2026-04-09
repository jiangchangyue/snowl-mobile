from __future__ import annotations

from dataclasses import dataclass, field

from snowl_mobile.core.validation import (
    expect_bool,
    expect_mapping_of_strings,
    expect_string,
    expect_string_list,
    get_optional,
    get_required,
)
from snowl_mobile.schemas.base import SchemaModel


@dataclass(frozen=True, slots=True)
class ModelSpec(SchemaModel):
    model_id: str
    provider: str
    api_style: str
    modalities: tuple[str, ...]
    supports_image_input: bool = False
    supports_tool_calling: bool = False
    supports_json_mode: bool = False
    rate_limit_profile: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict[str, object], path: str) -> "ModelSpec":
        spec = cls(
            model_id=expect_string(
                get_required(data, "model_id", path, aliases=("id",)),
                f"{path}.model_id",
            ),
            provider=expect_string(get_required(data, "provider", path), f"{path}.provider"),
            api_style=expect_string(get_required(data, "api_style", path), f"{path}.api_style"),
            modalities=expect_string_list(
                get_required(data, "modalities", path),
                f"{path}.modalities",
                allow_empty=False,
            ),
            supports_image_input=expect_bool(
                get_optional(data, "supports_image_input", False),
                f"{path}.supports_image_input",
            ),
            supports_tool_calling=expect_bool(
                get_optional(data, "supports_tool_calling", False),
                f"{path}.supports_tool_calling",
            ),
            supports_json_mode=expect_bool(
                get_optional(data, "supports_json_mode", False),
                f"{path}.supports_json_mode",
            ),
            rate_limit_profile=expect_mapping_of_strings(
                get_optional(data, "rate_limit_profile", {}),
                f"{path}.rate_limit_profile",
            ),
        )
        spec.validate(path)
        return spec

    def validate(self, path: str) -> None:
        if "image" in self.modalities and not self.supports_image_input:
            from snowl_mobile.core.errors import ConfigError

            raise ConfigError(
                "supports_image_input must be true when image is listed in modalities",
                path=f"{path}.supports_image_input",
            )
