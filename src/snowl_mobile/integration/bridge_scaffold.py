from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from string import Template

from snowl_mobile.adapters.bridges.contract import BridgeContract, BridgeContractValidator
from snowl_mobile.core.enums import IntegrationMode
from snowl_mobile.core.errors import IntegrationError


@dataclass(frozen=True, slots=True)
class BridgePackageScaffoldRequest:
    bridge_id: str
    agent_id: str
    benchmark_id: str
    output_dir: Path
    integration_mode: str = "wrap"
    requires_pair_recipe: bool = False
    package_name: str | None = None


@dataclass(frozen=True, slots=True)
class BridgePackageScaffoldResult:
    scaffold_root: Path
    generated_files: tuple[Path, ...]
    contract: BridgeContract


class BridgePackageScaffoldGenerator:
    """Generate a pair-specific bridge starter package."""

    def generate(self, request: BridgePackageScaffoldRequest) -> BridgePackageScaffoldResult:
        integration_mode = request.integration_mode.lower()
        if integration_mode not in {"wrap", "native", "hybrid"}:
            raise IntegrationError(f"unsupported bridge integration mode '{request.integration_mode}'")

        package_name = request.package_name or f"{request.bridge_id}_package"
        scaffold_root = request.output_dir / package_name
        tests_dir = scaffold_root / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        contract = BridgeContractValidator().validate(
            BridgeContract(
                bridge_id=request.bridge_id,
                agent_id=request.agent_id,
                benchmark_id=request.benchmark_id,
                integration_mode=IntegrationMode(integration_mode),
                observation_mapping_entry="TODO_observation_mapping_entry",
                action_mapping_entry="TODO_action_mapping_entry",
                run_entry="TODO_run_entry",
                environment_handshake_entry="TODO_environment_handshake_entry",
                artifact_capture_hooks=("TODO_artifact_capture_hook",),
                supported_backends=("TODO_backend",),
                required_env=("TODO_ENV_VAR",),
                requires_pair_recipe=request.requires_pair_recipe,
            )
        )
        context = self._context(contract)

        generated_files = [
            self._write_template(scaffold_root / "__init__.py", "bridge_package/__init__.py.tmpl", context),
            self._write_template(scaffold_root / "bridge.py", "bridge_package/bridge.py.tmpl", context),
            self._write_template(scaffold_root / "register.py", "bridge_package/register.py.tmpl", context),
            self._write_template(
                scaffold_root / "pair_runtime_recipe.example.yml",
                "bridge_package/pair_runtime_recipe.example.yml.tmpl",
                context,
            ),
            self._write_template(scaffold_root / "README.md", "bridge_package/README.md.tmpl", context),
            self._write_template(
                tests_dir / f"test_{request.bridge_id}_bridge.py",
                "bridge_package/test_bridge.py.tmpl",
                context,
            ),
        ]
        contract_path = scaffold_root / "contract.json"
        contract_path.write_text(json.dumps(contract.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        generated_files.append(contract_path)
        return BridgePackageScaffoldResult(
            scaffold_root=scaffold_root,
            generated_files=tuple(generated_files),
            contract=contract,
        )

    def _context(self, contract: BridgeContract) -> dict[str, str]:
        return {
            "bridge_id": contract.bridge_id,
            "class_name": self._class_name(contract.bridge_id),
            "agent_id": contract.agent_id,
            "benchmark_id": contract.benchmark_id,
            "integration_mode": contract.integration_mode.name,
            "integration_mode_lower": contract.integration_mode.value,
            "requires_pair_recipe": "True" if contract.requires_pair_recipe else "False",
            "requires_pair_recipe_json": "true" if contract.requires_pair_recipe else "false",
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
            raise IntegrationError(f"failed to load bridge template: {template_path}") from error

    def _class_name(self, bridge_id: str) -> str:
        normalized = bridge_id.replace("__", "_").replace("-", "_")
        return "".join(part.capitalize() for part in normalized.split("_") if part) + "BridgeAdapter"
