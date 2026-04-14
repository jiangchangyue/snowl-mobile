from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Sequence

from snowl_mobile.core.errors import IntegrationError


_PROJECT_ROOT_ENV_VAR = "SNOWL_MOBILE_PROJECT_ROOT"


def _looks_like_repository_root(candidate: Path) -> bool:
    return (
        (candidate / "pyproject.toml").is_file()
        and (candidate / "src" / "snowl_mobile").is_dir()
        and (candidate / "references").is_dir()
    )


def _discover_repository_root(start: Path) -> Path | None:
    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if _looks_like_repository_root(candidate):
            return candidate
    return None


def repository_root() -> Path:
    env_root = os.environ.get(_PROJECT_ROOT_ENV_VAR, "").strip()
    if env_root:
        resolved_env_root = _discover_repository_root(Path(env_root))
        if resolved_env_root is not None:
            return resolved_env_root

    # Prefer the caller's current workspace so an installed console script can
    # still use the references/ tree in the project the user is actively
    # working in.
    resolved_cwd_root = _discover_repository_root(Path.cwd())
    if resolved_cwd_root is not None:
        return resolved_cwd_root

    package_root = Path(__file__).resolve().parents[3]
    return _discover_repository_root(package_root) or package_root


def normalize_reference_candidate(candidate: Path, *, repo_root: Path | None = None) -> Path:
    root = repository_root() if repo_root is None else repo_root
    expanded = candidate.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (root / expanded).resolve()


def ordered_reference_candidates(
    *,
    default_candidates: Sequence[Path],
    requested_path: Path | None = None,
) -> tuple[list[Path], Path | None]:
    repo_root = repository_root()
    normalized_defaults = [
        normalize_reference_candidate(candidate, repo_root=repo_root)
        for candidate in default_candidates
    ]
    ignored_requested: Path | None = None
    if requested_path is None:
        return normalized_defaults, ignored_requested
    normalized_requested = normalize_reference_candidate(requested_path, repo_root=repo_root)
    if normalized_requested in normalized_defaults:
        return [normalized_requested, *[candidate for candidate in normalized_defaults if candidate != normalized_requested]], None
    ignored_requested = requested_path.expanduser()
    return normalized_defaults, ignored_requested


def resolve_repo_under_references(
    *,
    integration_name: str,
    default_candidates: Sequence[Path],
    requested_path: Path | None = None,
    exists_predicate: Callable[[Path], bool],
    expectation_description: str,
) -> Path:
    candidates, ignored_requested = ordered_reference_candidates(
        default_candidates=default_candidates,
        requested_path=requested_path,
    )
    for candidate in candidates:
        if exists_predicate(candidate):
            return candidate

    checked = ", ".join(candidate.as_posix() for candidate in candidates)
    example = default_candidates[0].as_posix() if default_candidates else "references/"
    ignored_hint = ""
    if ignored_requested is not None:
        ignored_hint = (
            f" Ignored external path '{ignored_requested.as_posix()}' because snowl-mobile now resolves "
            "this integration only from the local references/ tree."
        )
    raise IntegrationError(
        f"Unable to locate {integration_name} under references/. Checked: {checked}. "
        f"{expectation_description}. Please clone the upstream repository into {example} and retry."
        f"{ignored_hint}"
    )
