from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from string import Template

from snowl_mobile.core.errors import IntegrationError
from snowl_mobile.integration.benchmark_contract import (
    BenchmarkAdapterContract,
    BenchmarkContractValidator,
)
from snowl_mobile.integration.benchmark_inspector import BenchmarkRepositoryInspection


@dataclass(frozen=True, slots=True)
class BenchmarkPackageScaffoldRequest:
    adapter_id: str
    inspection: BenchmarkRepositoryInspection
    output_dir: Path
    integration_mode: str | None = None
    package_name: str | None = None


@dataclass(frozen=True, slots=True)
class BenchmarkPackageScaffoldResult:
    scaffold_root: Path
    generated_files: tuple[Path, ...]
    contract: BenchmarkAdapterContract

    def to_dict(self) -> dict[str, object]:
        return {
            "scaffold_root": str(self.scaffold_root),
            "generated_files": [str(path) for path in self.generated_files],
            "contract": self.contract.to_dict(),
        }


class BenchmarkPackageScaffoldGenerator:
    """Generate a benchmark integration starter package with aligned templates."""

    def generate(self, request: BenchmarkPackageScaffoldRequest) -> BenchmarkPackageScaffoldResult:
        integration_mode = (request.integration_mode or request.inspection.suggested_integration_mode).lower()
        if integration_mode not in {"wrap", "native", "hybrid"}:
            raise IntegrationError(f"unsupported benchmark integration mode '{integration_mode}'")

        package_name = request.package_name or f"{request.adapter_id}_package"
        scaffold_root = request.output_dir / package_name
        tests_dir = scaffold_root / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        contract = BenchmarkContractValidator().validate(request.inspection.default_contract())
        context = self._context(
            adapter_id=request.adapter_id,
            inspection=request.inspection,
            integration_mode=integration_mode,
            contract=contract,
        )

        generated_files = [
            self._write_template(scaffold_root / "__init__.py", "benchmark_package/__init__.py.tmpl", context),
            self._write_template(scaffold_root / "adapter.py", "benchmark_package/adapter.py.tmpl", context),
            self._write_template(scaffold_root / "register.py", "benchmark_package/register.py.tmpl", context),
            self._write_template(
                scaffold_root / "config.example.yml",
                "benchmark_package/config.example.yml.tmpl",
                context,
            ),
            self._write_template(scaffold_root / "README.md", "benchmark_package/README.md.tmpl", context),
            self._write_template(
                tests_dir / f"test_{request.adapter_id}_integration.py",
                "benchmark_package/test_integration.py.tmpl",
                context,
            ),
        ]
        contract_path = scaffold_root / "contract.json"
        contract_path.write_text(json.dumps(contract.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        generated_files.append(contract_path)
        return BenchmarkPackageScaffoldResult(
            scaffold_root=scaffold_root,
            generated_files=tuple(generated_files),
            contract=contract,
        )

    def _context(
        self,
        *,
        adapter_id: str,
        inspection: BenchmarkRepositoryInspection,
        integration_mode: str,
        contract: BenchmarkAdapterContract,
    ) -> dict[str, str]:
        first_mapping = contract.native_metric_mappings[0]
        return {
            "adapter_id": adapter_id,
            "class_name": self._class_name(adapter_id),
            "display_name": adapter_id.replace("_", " ").title(),
            "repo_name": inspection.repo_name,
            "repo_path": self._display_repo_path(inspection),
            "integration_mode": integration_mode.upper(),
            "integration_mode_lower": integration_mode.lower(),
            "required_env": self._python_tuple(inspection.dependency_hints[:4]),
            "task_discovery_entry": contract.task_discovery_entry,
            "environment_init_entry": contract.environment_init_entry,
            "pre_task_setup_entry": contract.pre_task_setup_entry,
            "reset_entry": contract.reset_entry,
            "run_entry": contract.run_entry,
            "score_capture_entry": contract.score_capture_entry,
            "cleanup_entry": contract.cleanup_entry,
            "observation_form": contract.observation_form,
            "action_execution_path": contract.action_execution_path,
            "raw_artifact_capture_points": ", ".join(contract.raw_artifact_capture_points),
            "primary_native_metric": first_mapping.native_metric,
            "primary_platform_metric": first_mapping.platform_metric,
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
            raise IntegrationError(f"failed to load benchmark template: {template_path}") from error

    def _class_name(self, adapter_id: str) -> str:
        return "".join(part.capitalize() for part in adapter_id.split("_")) + "Adapter"

    def _display_repo_path(self, inspection: BenchmarkRepositoryInspection) -> str:
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
