from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from snowl_mobile.core.errors import IntegrationError


_VALID_KINDS = {"agent", "benchmark"}
_ENTRYPOINT_FILENAMES = {
    "__main__.py",
    "app.py",
    "benchmark_runner.py",
    "cli.py",
    "main.py",
    "manage.py",
    "run.py",
    "runner.py",
}
_ENV_FILENAMES = {
    ".env",
    ".env.example",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "environment.yml",
    "environment.yaml",
}


@dataclass(frozen=True, slots=True)
class RepositoryInspection:
    repo_name: str
    repo_kind: str
    repo_path: Path
    readme_files: tuple[str, ...]
    requirements_files: tuple[str, ...]
    project_files: tuple[str, ...]
    entrypoints: tuple[str, ...]
    package_roots: tuple[str, ...]
    dependency_hints: tuple[str, ...]
    env_files: tuple[str, ...]
    summary_excerpt: str
    suggested_integration_mode: str
    rationale: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "repo_name": self.repo_name,
            "repo_kind": self.repo_kind,
            "repo_path": str(self.repo_path),
            "readme_files": list(self.readme_files),
            "requirements_files": list(self.requirements_files),
            "project_files": list(self.project_files),
            "entrypoints": list(self.entrypoints),
            "package_roots": list(self.package_roots),
            "dependency_hints": list(self.dependency_hints),
            "env_files": list(self.env_files),
            "summary_excerpt": self.summary_excerpt,
            "suggested_integration_mode": self.suggested_integration_mode,
            "rationale": list(self.rationale),
        }


class RepositoryInspector:
    """Inspect a local third-party repository that has already been cloned by the user."""

    def inspect(self, repo_path: Path, *, repo_kind: str) -> RepositoryInspection:
        normalized_kind = repo_kind.strip().lower()
        if normalized_kind not in _VALID_KINDS:
            allowed = ", ".join(sorted(_VALID_KINDS))
            raise IntegrationError(f"unsupported repository kind '{repo_kind}' (allowed: {allowed})")
        if not repo_path.exists():
            raise IntegrationError(f"repository path does not exist: {repo_path}")
        if not repo_path.is_dir():
            raise IntegrationError(f"repository path is not a directory: {repo_path}")

        resolved = repo_path.resolve()
        readme_files = self._collect_readmes(resolved)
        requirements_files = self._collect_requirement_files(resolved)
        project_files = self._collect_project_files(resolved)
        entrypoints = self._collect_entrypoints(
            resolved=resolved,
            project_files=project_files,
        )
        package_roots = self._collect_package_roots(resolved)
        dependency_hints = self._collect_dependency_hints(resolved, requirements_files, project_files)
        env_files = self._collect_env_files(resolved)
        summary_excerpt = self._summarize_readme(resolved, readme_files)
        suggested_mode, rationale = self._suggest_mode(
            repo_kind=normalized_kind,
            entrypoints=entrypoints,
            package_roots=package_roots,
            dependency_hints=dependency_hints,
        )
        return RepositoryInspection(
            repo_name=resolved.name,
            repo_kind=normalized_kind,
            repo_path=resolved,
            readme_files=readme_files,
            requirements_files=requirements_files,
            project_files=project_files,
            entrypoints=entrypoints,
            package_roots=package_roots,
            dependency_hints=dependency_hints,
            env_files=env_files,
            summary_excerpt=summary_excerpt,
            suggested_integration_mode=suggested_mode,
            rationale=rationale,
        )

    def _collect_readmes(self, resolved: Path) -> tuple[str, ...]:
        candidates = [
            path.relative_to(resolved).as_posix()
            for path in resolved.iterdir()
            if path.is_file() and path.name.lower().startswith("readme")
        ]
        return tuple(sorted(candidates))

    def _collect_requirement_files(self, resolved: Path) -> tuple[str, ...]:
        candidates = {
            path.relative_to(resolved).as_posix()
            for path in resolved.rglob("*")
            if path.is_file()
            and (
                path.name.startswith("requirements")
                or path.name in {"environment.yml", "environment.yaml"}
            )
        }
        return tuple(sorted(candidates))

    def _collect_project_files(self, resolved: Path) -> tuple[str, ...]:
        candidates: list[str] = []
        for name in ("pyproject.toml", "setup.py", "setup.cfg"):
            candidate = resolved / name
            if candidate.exists():
                candidates.append(candidate.relative_to(resolved).as_posix())
        return tuple(sorted(candidates))

    def _collect_entrypoints(
        self,
        *,
        resolved: Path,
        project_files: tuple[str, ...],
    ) -> tuple[str, ...]:
        candidates = {
            path.relative_to(resolved).as_posix()
            for path in resolved.rglob("*.py")
            if path.name in _ENTRYPOINT_FILENAMES
            or "cli" in path.stem.lower()
            or path.stem.lower().startswith("run")
        }

        pyproject_path = resolved / "pyproject.toml"
        if "pyproject.toml" in project_files and pyproject_path.exists():
            candidates.update(self._pyproject_entrypoints(pyproject_path))
        return tuple(sorted(candidates))

    def _collect_package_roots(self, resolved: Path) -> tuple[str, ...]:
        candidates = {
            init_path.parent.relative_to(resolved).as_posix()
            for init_path in resolved.rglob("__init__.py")
            if ".venv" not in init_path.parts and "__pycache__" not in init_path.parts
        }
        return tuple(sorted(candidates))

    def _collect_dependency_hints(
        self,
        resolved: Path,
        requirements_files: tuple[str, ...],
        project_files: tuple[str, ...],
    ) -> tuple[str, ...]:
        dependencies: list[str] = []
        for relative in requirements_files:
            candidate = resolved / relative
            if candidate.suffix not in {".txt", ".yml", ".yaml"}:
                continue
            dependencies.extend(self._parse_requirement_lines(candidate))

        if "pyproject.toml" in project_files:
            dependencies.extend(self._parse_pyproject_dependencies(resolved / "pyproject.toml"))

        unique: list[str] = []
        seen: set[str] = set()
        for dependency in dependencies:
            lowered = dependency.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            unique.append(lowered)
        return tuple(unique[:12])

    def _collect_env_files(self, resolved: Path) -> tuple[str, ...]:
        candidates = {
            path.relative_to(resolved).as_posix()
            for path in resolved.rglob("*")
            if path.is_file() and path.name in _ENV_FILENAMES
        }
        return tuple(sorted(candidates))

    def _summarize_readme(self, resolved: Path, readme_files: tuple[str, ...]) -> str:
        if not readme_files:
            return ""
        readme_path = resolved / readme_files[0]
        try:
            text = readme_path.read_text(encoding="utf-8")
        except OSError:
            return ""

        lines = [
            line.strip().lstrip("#").strip()
            for line in text.splitlines()
            if line.strip()
        ]
        if not lines:
            return ""
        excerpt = " ".join(lines[:3])
        return excerpt[:240]

    def _suggest_mode(
        self,
        *,
        repo_kind: str,
        entrypoints: tuple[str, ...],
        package_roots: tuple[str, ...],
        dependency_hints: tuple[str, ...],
    ) -> tuple[str, tuple[str, ...]]:
        reasons: list[str] = []
        if entrypoints:
            reasons.append("detected explicit runnable entrypoints")
        if package_roots:
            reasons.append("detected importable Python package roots")
        if dependency_hints:
            reasons.append("detected dependency manifests that likely require isolated environments")

        if repo_kind == "benchmark":
            if entrypoints:
                reasons.append("benchmark repos usually integrate fastest via wrap mode first")
                return "wrap", tuple(reasons)
            if package_roots:
                reasons.append("benchmark exposes Python packages, so hybrid is a reasonable next step")
                return "hybrid", tuple(reasons)
            reasons.append("no clear package API was detected, so wrap mode is the safer default")
            return "wrap", tuple(reasons)

        if package_roots and entrypoints:
            reasons.append("agent exposes both package APIs and runnable scripts, which fits hybrid mode")
            return "hybrid", tuple(reasons)
        if package_roots:
            reasons.append("agent looks importable enough to start with native mode")
            return "native", tuple(reasons)
        reasons.append("no stable import surface was detected, so wrap mode is the safer default")
        return "wrap", tuple(reasons)

    def _parse_requirement_lines(self, path: Path) -> list[str]:
        dependencies: list[str] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return dependencies

        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("-r "):
                continue
            dependency = re.split(r"[<>=!~;\[]", line, maxsplit=1)[0].strip()
            if dependency:
                dependencies.append(dependency)
        return dependencies

    def _parse_pyproject_dependencies(self, path: Path) -> list[str]:
        dependencies: list[str] = []
        try:
            payload = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return dependencies

        project = payload.get("project", {})
        if isinstance(project, dict):
            raw_dependencies = project.get("dependencies", [])
            if isinstance(raw_dependencies, list):
                for dependency in raw_dependencies:
                    if isinstance(dependency, str):
                        parsed = re.split(r"[<>=!~;\[]", dependency, maxsplit=1)[0].strip()
                        if parsed:
                            dependencies.append(parsed)
        return dependencies

    def _pyproject_entrypoints(self, path: Path) -> set[str]:
        candidates: set[str] = set()
        try:
            payload = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return candidates

        project = payload.get("project", {})
        if isinstance(project, dict):
            scripts = project.get("scripts", {})
            if isinstance(scripts, dict):
                for name, target in scripts.items():
                    candidates.add(f"pyproject:script:{name}={target}")

        tool = payload.get("tool", {})
        if isinstance(tool, dict):
            poetry = tool.get("poetry", {})
            if isinstance(poetry, dict):
                scripts = poetry.get("scripts", {})
                if isinstance(scripts, dict):
                    for name, target in scripts.items():
                        candidates.add(f"pyproject:poetry-script:{name}={target}")
        return candidates
