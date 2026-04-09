from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from string import Template

from snowl_mobile.core.errors import IntegrationError
from snowl_mobile.integration.agent_contract import AgentAdapterContract, AgentContractValidator
from snowl_mobile.integration.agent_inspector import AgentRepositoryInspection


@dataclass(frozen=True, slots=True)
class AgentPackageScaffoldRequest:
    adapter_id: str
    inspection: AgentRepositoryInspection
    output_dir: Path
    integration_mode: str | None = None
    capability_profile: str = "auto"
    package_name: str | None = None


@dataclass(frozen=True, slots=True)
class AgentPackageScaffoldResult:
    scaffold_root: Path
    generated_files: tuple[Path, ...]
    contract: AgentAdapterContract

    def to_dict(self) -> dict[str, object]:
        return {
            "scaffold_root": str(self.scaffold_root),
            "generated_files": [str(path) for path in self.generated_files],
            "contract": self.contract.to_dict(),
        }


class AgentPackageScaffoldGenerator:
    """Generate an agent integration starter package with aligned templates."""

    def generate(self, request: AgentPackageScaffoldRequest) -> AgentPackageScaffoldResult:
        integration_mode = (request.integration_mode or request.inspection.suggested_integration_mode).lower()
        if integration_mode not in {"wrap", "native", "hybrid"}:
            raise IntegrationError(f"unsupported agent integration mode '{integration_mode}'")
        capability_profile = request.capability_profile.lower()
        if capability_profile not in {"auto", "text-only", "vision-capable"}:
            raise IntegrationError(f"unsupported agent capability profile '{request.capability_profile}'")

        package_name = request.package_name or f"{request.adapter_id}_package"
        scaffold_root = request.output_dir / package_name
        tests_dir = scaffold_root / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        contract = AgentContractValidator().validate(
            request.inspection.default_contract(capability_profile=capability_profile)
        )
        context = self._context(
            adapter_id=request.adapter_id,
            inspection=request.inspection,
            integration_mode=integration_mode,
            capability_profile=capability_profile,
            contract=contract,
        )

        generated_files = [
            self._write_template(scaffold_root / "__init__.py", "agent_package/__init__.py.tmpl", context),
            self._write_template(scaffold_root / "adapter.py", "agent_package/adapter.py.tmpl", context),
            self._write_template(scaffold_root / "register.py", "agent_package/register.py.tmpl", context),
            self._write_template(
                scaffold_root / "capability.json",
                "agent_package/capability.json.tmpl",
                context,
            ),
            self._write_template(
                scaffold_root / "config.example.yml",
                "agent_package/config.example.yml.tmpl",
                context,
            ),
            self._write_template(scaffold_root / "README.md", "agent_package/README.md.tmpl", context),
            self._write_template(
                tests_dir / f"test_{request.adapter_id}_integration.py",
                "agent_package/test_integration.py.tmpl",
                context,
            ),
        ]
        contract_path = scaffold_root / "contract.json"
        contract_path.write_text(json.dumps(contract.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        generated_files.append(contract_path)
        return AgentPackageScaffoldResult(
            scaffold_root=scaffold_root,
            generated_files=tuple(generated_files),
            contract=contract,
        )

    def _context(
        self,
        *,
        adapter_id: str,
        inspection: AgentRepositoryInspection,
        integration_mode: str,
        capability_profile: str,
        contract: AgentAdapterContract,
    ) -> dict[str, str]:
        capability = contract.capability
        model_ref = "dummy_vision_model" if "image" in capability.input_modalities else "dummy_text_model"
        worker_mode = "IN_PROCESS" if integration_mode == "native" else "VENV"
        worker_mode_lower = "in_process" if integration_mode == "native" else "venv"
        return {
            "adapter_id": adapter_id,
            "class_name": self._class_name(adapter_id),
            "display_name": adapter_id.replace("_", " ").title(),
            "repo_name": inspection.repo_name,
            "repo_path": self._display_repo_path(inspection),
            "integration_mode": integration_mode.upper(),
            "integration_mode_lower": integration_mode.lower(),
            "capability_profile": capability_profile,
            "worker_mode": worker_mode,
            "worker_mode_lower": worker_mode_lower,
            "required_env": self._python_tuple(capability.runtime_requirements[:4]),
            "required_env_json": self._json_list(capability.runtime_requirements[:4]),
            "input_modalities": self._python_tuple(capability.input_modalities),
            "input_modalities_json": self._json_list(capability.input_modalities),
            "input_modalities_text": ", ".join(capability.input_modalities),
            "supported_model_protocols": self._python_tuple(capability.supported_model_protocols),
            "supported_model_protocols_json": self._json_list(capability.supported_model_protocols),
            "supported_model_protocols_text": ", ".join(capability.supported_model_protocols),
            "tool_backends": ", ".join(capability.tool_backends),
            "tool_backends_json": self._json_list(capability.tool_backends),
            "human_confirmation_mode": capability.human_confirmation_mode,
            "action_output_schema": capability.action_output_schema,
            "model_ref": model_ref,
            "supports_image_input": "True" if capability.supports_image_input else "False",
            "supports_image_input_json": "true" if capability.supports_image_input else "false",
            "supports_json_mode": "True" if capability.supports_json_mode else "False",
            "supports_json_mode_json": "true" if capability.supports_json_mode else "false",
            "supports_tool_calling": "True" if capability.supports_tool_calling else "False",
            "supports_tool_calling_json": "true" if capability.supports_tool_calling else "false",
            "requires_tool_calling": "True" if capability.requires_tool_calling else "False",
            "requires_tool_calling_json": "true" if capability.requires_tool_calling else "false",
            "requires_json_mode": "True" if capability.requires_json_mode else "False",
            "requires_json_mode_json": "true" if capability.requires_json_mode else "false",
            "observation_transform_entry": contract.observation_transform_entry,
            "step_entry": contract.step_entry,
            "run_entry": contract.run_entry,
            "action_normalization_entry": contract.action_normalization_entry,
            "model_call_entry": contract.model_call_entry,
            "device_control_entry": contract.device_control_entry,
            "raw_output_capture_points": ", ".join(contract.raw_output_capture_points),
            "raw_output_capture_points_json": self._json_list(contract.raw_output_capture_points),
            "summary_excerpt": inspection.summary_excerpt or "No README summary was detected.",
        }

    def _write_template(self, path: Path, template_name: str, context: dict[str, str]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        rendered = Template(self._template_text(template_name)).substitute(context)
        path.write_text(rendered, encoding="utf-8")
        return path

    def _template_text(self, template_name: str) -> str:
        template_path = Path(__file__).with_name("templates") / template_name
        try:
            return template_path.read_text(encoding="utf-8")
        except OSError as error:
            raise IntegrationError(f"failed to load agent template: {template_path}") from error

    def _class_name(self, adapter_id: str) -> str:
        return "".join(part.capitalize() for part in adapter_id.split("_")) + "Adapter"

    def _display_repo_path(self, inspection: AgentRepositoryInspection) -> str:
        try:
            return inspection.repo_path.relative_to(Path.cwd()).as_posix()
        except ValueError:
            return inspection.repo_path.as_posix()

    def _python_tuple(self, values: tuple[str, ...] | list[str]) -> str:
        items = list(values)
        if not items:
            return "()"
        rendered = ", ".join(repr(item) for item in items)
        if len(items) == 1:
            return f"({rendered},)"
        return f"({rendered})"

    def _json_list(self, values: tuple[str, ...] | list[str]) -> str:
        items = list(values)
        if not items:
            return "[]"
        rendered = ", ".join(f'"{item}"' for item in items)
        return f"[{rendered}]"
