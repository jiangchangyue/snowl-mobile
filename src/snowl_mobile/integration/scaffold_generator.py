from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from string import Template

from snowl_mobile.core.errors import IntegrationError
from snowl_mobile.integration.repo_inspector import RepositoryInspection


@dataclass(frozen=True, slots=True)
class ScaffoldRequest:
    repo_kind: str
    adapter_id: str
    inspection: RepositoryInspection
    output_path: Path
    class_name: str | None = None


@dataclass(frozen=True, slots=True)
class ScaffoldResult:
    output_path: Path
    class_name: str
    content: str


class AdapterScaffoldGenerator:
    """Render adapter starter files from the current platform contracts."""

    def generate(self, request: ScaffoldRequest) -> ScaffoldResult:
        if request.repo_kind not in {"agent", "benchmark"}:
            raise IntegrationError(f"unsupported scaffold kind '{request.repo_kind}'")
        class_name = request.class_name or self._default_class_name(request.adapter_id)
        content = (
            self._render_agent(request, class_name)
            if request.repo_kind == "agent"
            else self._render_benchmark(request, class_name)
        )
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        request.output_path.write_text(content, encoding="utf-8")
        return ScaffoldResult(
            output_path=request.output_path,
            class_name=class_name,
            content=content,
        )

    def _render_agent(self, request: ScaffoldRequest, class_name: str) -> str:
        inspection = request.inspection
        template = Template(self._template_text("agent_adapter.py.tmpl"))
        required_env = self._python_tuple(inspection.dependency_hints[:4])
        modalities = self._agent_modalities(inspection)
        supported_modalities = self._python_tuple(modalities)
        required_modalities = self._python_tuple(("text",))
        context = {
            "adapter_id": request.adapter_id,
            "class_name": class_name,
            "repo_name": inspection.repo_name,
            "repo_path": self._display_repo_path(inspection),
            "display_name": self._display_name(request.adapter_id),
            "integration_mode": inspection.suggested_integration_mode.upper(),
            "worker_mode": self._agent_worker_mode(inspection.suggested_integration_mode),
            "required_env": required_env,
            "supported_modalities": supported_modalities,
            "required_modalities": required_modalities,
            "supports_image_input": "True" if "image" in modalities else "False",
            "supports_json_mode": "True" if inspection.suggested_integration_mode != "native" else "False",
            "summary_excerpt": inspection.summary_excerpt or "No README summary was detected.",
            "supported_benchmarks": self._python_tuple(("TODO_benchmark_id",)),
        }
        return template.substitute(context)

    def _render_benchmark(self, request: ScaffoldRequest, class_name: str) -> str:
        inspection = request.inspection
        template = Template(self._template_text("benchmark_adapter.py.tmpl"))
        required_env = self._python_tuple(inspection.dependency_hints[:4])
        context = {
            "adapter_id": request.adapter_id,
            "class_name": class_name,
            "repo_name": inspection.repo_name,
            "repo_path": self._display_repo_path(inspection),
            "display_name": self._display_name(request.adapter_id),
            "integration_mode": inspection.suggested_integration_mode.upper(),
            "required_env": required_env,
            "summary_excerpt": inspection.summary_excerpt or "No README summary was detected.",
        }
        return template.substitute(context)

    def _template_text(self, filename: str) -> str:
        template_path = Path(__file__).with_name("templates") / filename
        try:
            return template_path.read_text(encoding="utf-8")
        except OSError as error:
            raise IntegrationError(f"failed to load template: {template_path}") from error

    def _default_class_name(self, adapter_id: str) -> str:
        parts = [part for part in adapter_id.replace("-", "_").split("_") if part]
        return "".join(part.capitalize() for part in parts) + "Adapter"

    def _display_name(self, adapter_id: str) -> str:
        return adapter_id.replace("_", " ").replace("-", " ").title()

    def _display_repo_path(self, inspection: RepositoryInspection) -> str:
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

    def _agent_modalities(self, inspection: RepositoryInspection) -> tuple[str, ...]:
        image_hints = ("opencv", "pillow", "torchvision", "uiautomator")
        if any(any(token in dependency for token in image_hints) for dependency in inspection.dependency_hints):
            return ("text", "image")
        return ("text",)

    def _agent_worker_mode(self, integration_mode: str) -> str:
        if integration_mode == "native":
            return "IN_PROCESS"
        return "VENV"
