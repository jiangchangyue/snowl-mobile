from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from snowl_mobile.core.errors import IntegrationError


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


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
