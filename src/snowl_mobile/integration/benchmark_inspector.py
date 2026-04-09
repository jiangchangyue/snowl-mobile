from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from snowl_mobile.integration.benchmark_contract import (
    BenchmarkAdapterContract,
    BenchmarkContractValidator,
    NativeMetricMapping,
)
from snowl_mobile.integration.repo_inspector import RepositoryInspection, RepositoryInspector


@dataclass(frozen=True, slots=True)
class BenchmarkRepositoryInspection:
    base: RepositoryInspection
    examples_dirs: tuple[str, ...]
    evaluation_entrypoints: tuple[str, ...]
    task_discovery_candidates: tuple[str, ...]
    environment_init_candidates: tuple[str, ...]
    reset_candidates: tuple[str, ...]
    scorer_candidates: tuple[str, ...]
    observation_forms: tuple[str, ...]
    action_execution_candidates: tuple[str, ...]
    raw_artifact_capture_points: tuple[str, ...]

    @property
    def repo_name(self) -> str:
        return self.base.repo_name

    @property
    def repo_path(self) -> Path:
        return self.base.repo_path

    @property
    def suggested_integration_mode(self) -> str:
        return self.base.suggested_integration_mode

    @property
    def dependency_hints(self) -> tuple[str, ...]:
        return self.base.dependency_hints

    @property
    def summary_excerpt(self) -> str:
        return self.base.summary_excerpt

    def to_dict(self) -> dict[str, object]:
        payload = self.base.to_dict()
        payload.update(
            {
                "examples_dirs": list(self.examples_dirs),
                "evaluation_entrypoints": list(self.evaluation_entrypoints),
                "task_discovery_candidates": list(self.task_discovery_candidates),
                "environment_init_candidates": list(self.environment_init_candidates),
                "reset_candidates": list(self.reset_candidates),
                "scorer_candidates": list(self.scorer_candidates),
                "observation_forms": list(self.observation_forms),
                "action_execution_candidates": list(self.action_execution_candidates),
                "raw_artifact_capture_points": list(self.raw_artifact_capture_points),
            }
        )
        return payload

    def default_contract(self) -> BenchmarkAdapterContract:
        contract = BenchmarkAdapterContract(
            task_discovery_entry=self._best_candidate(
                self.task_discovery_candidates,
                "TODO_task_discovery_entry",
            ),
            environment_init_entry=self._best_candidate(
                self.environment_init_candidates or self.reset_candidates,
                "TODO_environment_init_entry",
            ),
            pre_task_setup_entry="prepare_trial",
            reset_entry=self._best_candidate(self.reset_candidates, "TODO_reset_entry"),
            run_entry=self._best_candidate(self.evaluation_entrypoints, "TODO_run_entry"),
            score_capture_entry=self._best_candidate(
                self.scorer_candidates,
                "TODO_score_capture_entry",
            ),
            cleanup_entry=self._best_candidate(self.reset_candidates, "TODO_cleanup_entry"),
            observation_form=self._best_candidate(self.observation_forms, "benchmark_native"),
            action_execution_path=self._best_candidate(
                self.action_execution_candidates,
                "TODO_action_execution_path",
            ),
            raw_artifact_capture_points=self.raw_artifact_capture_points
            or ("TODO_raw_artifact_capture_point",),
            native_metric_mappings=(
                NativeMetricMapping(
                    native_metric="TODO_native_metric",
                    platform_metric="task_success",
                    rationale="Map the benchmark-native success metric into the primary platform metric.",
                ),
            ),
        )
        return BenchmarkContractValidator().validate(contract)

    def _best_candidate(self, values: tuple[str, ...], fallback: str) -> str:
        if not values:
            return fallback
        for value in values:
            if "/" in value or "." in Path(value).name:
                return value
        return values[0]


class BenchmarkRepositoryInspector:
    """Richer benchmark-specific inspection built on top of the generic local repo inspector."""

    def __init__(self, *, base_inspector: RepositoryInspector | None = None) -> None:
        self.base_inspector = base_inspector or RepositoryInspector()

    def inspect(self, repo_path: Path) -> BenchmarkRepositoryInspection:
        base = self.base_inspector.inspect(repo_path, repo_kind="benchmark")
        resolved = base.repo_path
        examples_dirs = self._collect_examples_dirs(resolved)
        evaluation_entrypoints = self._collect_candidates(
            resolved,
            keywords=("eval", "evaluate", "score", "scorer", "runner", "benchmark_runner", "environment"),
            include_dirs=False,
        )
        task_discovery_candidates = self._collect_candidates(
            resolved,
            keywords=("task", "dataset", "manifest", "case", "scenario"),
        )
        environment_init_candidates = self._collect_candidates(
            resolved,
            keywords=("setup", "prepare", "init", "bootstrap", "seed", "fixture", "environment"),
        )
        reset_candidates = self._collect_candidates(
            resolved,
            keywords=("reset", "cleanup", "teardown", "restore", "snapshot"),
        )
        scorer_candidates = self._collect_candidates(
            resolved,
            keywords=("score", "metric", "eval", "evaluate", "scorer"),
        )
        action_execution_candidates = self._collect_candidates(
            resolved,
            keywords=("action", "execute", "executor", "runner", "adb", "appium", "parser"),
        )
        raw_artifact_capture_points = self._collect_candidates(
            resolved,
            keywords=("artifact", "screenshot", "xml", "hierarchy", "trace", "log", "logger"),
        )
        observation_forms = self._infer_observation_forms(resolved)

        merged_eval = tuple(dict.fromkeys((*base.entrypoints, *evaluation_entrypoints)))
        return BenchmarkRepositoryInspection(
            base=base,
            examples_dirs=examples_dirs,
            evaluation_entrypoints=merged_eval,
            task_discovery_candidates=task_discovery_candidates,
            environment_init_candidates=environment_init_candidates,
            reset_candidates=reset_candidates,
            scorer_candidates=scorer_candidates,
            observation_forms=observation_forms,
            action_execution_candidates=action_execution_candidates,
            raw_artifact_capture_points=raw_artifact_capture_points,
        )

    def _collect_examples_dirs(self, resolved: Path) -> tuple[str, ...]:
        candidates = {
            path.relative_to(resolved).as_posix()
            for path in resolved.rglob("*")
            if path.is_dir() and path.name.lower() in {"example", "examples", "sample", "samples"}
        }
        return tuple(sorted(candidates))

    def _collect_candidates(
        self,
        resolved: Path,
        *,
        keywords: tuple[str, ...],
        include_dirs: bool = True,
        include_files: bool = True,
    ) -> tuple[str, ...]:
        candidates: set[str] = set()
        ignored_suffixes = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".pdf"}
        for path in resolved.rglob("*"):
            if any(part in {".git", ".venv", "__pycache__"} for part in path.parts):
                continue
            if path.is_dir() and not include_dirs:
                continue
            if path.is_file() and not include_files:
                continue
            if path.is_file() and path.suffix.lower() in ignored_suffixes:
                continue
            lowered = path.name.lower()
            if any(keyword in lowered for keyword in keywords):
                candidates.add(path.relative_to(resolved).as_posix())
        return tuple(sorted(candidates))

    def _infer_observation_forms(self, resolved: Path) -> tuple[str, ...]:
        detected: list[str] = []
        all_names = [path.name.lower() for path in resolved.rglob("*") if path.is_file()]
        all_text = self._sample_text(resolved)
        if any(token in name for name in all_names for token in ("xml", "hierarchy", "uiautomator", "layout")) or any(
            token in all_text for token in ("xml", "hierarchy", "ui_tree", "uiautomator")
        ):
            detected.append("ui_tree")
        if any(token in name for name in all_names for token in ("image", "screen", "screenshot", "vision")) or any(
            token in all_text for token in ("image", "screen", "screenshot", "vision")
        ):
            detected.append("image")
        if any(token in name for name in all_names for token in ("json", "text", "manifest")) or any(
            token in all_text for token in ("json", "text", "manifest")
        ):
            detected.append("structured_text")
        if not detected:
            detected.append("benchmark_native")
        return tuple(dict.fromkeys(detected))

    def _sample_text(self, resolved: Path) -> str:
        chunks: list[str] = []
        for path in resolved.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".md", ".txt", ".json", ".yaml", ".yml"}:
                continue
            try:
                chunks.append(path.read_text(encoding="utf-8").lower())
            except OSError:
                continue
            if len(chunks) >= 12:
                break
        return "\n".join(chunks)
