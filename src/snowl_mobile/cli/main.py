from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from snowl_mobile.adapters.builtin import create_builtin_registry
from snowl_mobile.artifacts.paths import slugify
from snowl_mobile.artifacts.store import ArtifactStore
from snowl_mobile.core.config_loader import load_project_spec
from snowl_mobile.core.enums import DeviceMode
from snowl_mobile.core.errors import ArtifactError, SnowlMobileError
from snowl_mobile.core.logging import configure_logging
from snowl_mobile.core.planner import ExecutionPlanner
from snowl_mobile.core.run_context import RunContext
from snowl_mobile.core.states import RunStatus, TrialStatus
from snowl_mobile.devices.demo import run_fake_emulator_demo
from snowl_mobile.devices.emulator_instance import HealthStatus
from snowl_mobile.devices.emulator_pool import create_emulator_pool_manager
from snowl_mobile.integration.agent_checklist import AgentIntegrationChecklistGenerator
from snowl_mobile.integration.agent_inspector import AgentRepositoryInspector
from snowl_mobile.integration.agent_scaffold import (
    AgentPackageScaffoldGenerator,
    AgentPackageScaffoldRequest,
)
from snowl_mobile.integration.benchmark_checklist import (
    BenchmarkIntegrationChecklistGenerator,
)
from snowl_mobile.integration.benchmark_inspector import BenchmarkRepositoryInspector
from snowl_mobile.integration.benchmark_scaffold import (
    BenchmarkPackageScaffoldGenerator,
    BenchmarkPackageScaffoldRequest,
)
from snowl_mobile.integration.bridge_scaffold import (
    BridgePackageScaffoldGenerator,
    BridgePackageScaffoldRequest,
)
from snowl_mobile.integration.checklist_generator import IntegrationChecklistGenerator
from snowl_mobile.integration.repo_inspector import RepositoryInspector
from snowl_mobile.integration.scaffold_generator import (
    AdapterScaffoldGenerator,
    ScaffoldRequest,
)
from snowl_mobile.runtime.trial_orchestrator import TrialOrchestrator
from snowl_mobile.schedulers.retry_controller import RetryController
from snowl_mobile.scoring.run_eval_results import build_run_eval_results


LOGGER = logging.getLogger(__name__)
_TERMINAL_TRIAL_STATUSES = {
    TrialStatus.COMPLETED.value,
    TrialStatus.FAILED.value,
    TrialStatus.SKIPPED.value,
    TrialStatus.ABORTED.value,
}


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _add_device_override_arguments(
    parser: argparse.ArgumentParser,
    *,
    default_device_mode: str | None = None,
) -> None:
    parser.add_argument(
        "--device-mode",
        choices=tuple(mode.value for mode in DeviceMode),
        default=default_device_mode,
        help="Override the configured device backend mode.",
    )
    parser.add_argument(
        "--adb-serial",
        dest="adb_serials",
        action="append",
        help="Restrict real-device discovery to one adb serial. Repeat to add more.",
    )
    parser.add_argument(
        "--avd-name",
        dest="avd_names",
        action="append",
        help="Restrict real-device discovery to one AVD name. Repeat to add more.",
    )


def _add_runtime_override_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--batch-size",
        type=int,
        help="Override runtime.batch_size for this invocation.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        help="Override runtime.max_steps for this invocation.",
    )


def _add_model_override_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--model-name",
        help="Override the configured model id for single-model run configs.",
    )
    parser.add_argument(
        "--base-url",
        help="Set PHONE_AGENT_BASE_URL for this invocation.",
    )
    parser.add_argument(
        "--api-key",
        help="Set PHONE_AGENT_API_KEY for this invocation.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="snowl-mobile",
        description="Bootstrap and validate the snowl-mobile evaluation platform.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase log verbosity.",
    )

    subparsers = parser.add_subparsers(dest="command")

    validate_parser = subparsers.add_parser(
        "validate-config",
        aliases=["validate"],
        help="Validate a project config.",
    )
    validate_parser.add_argument("config", help="Path to a project YAML file.")
    validate_parser.set_defaults(handler=_handle_validate)

    plan_parser = subparsers.add_parser(
        "plan",
        help="Expand the execution plan and print planned trials without simulating execution.",
    )
    plan_parser.add_argument("config", help="Path to a project YAML file.")
    plan_parser.set_defaults(handler=_handle_plan)

    dry_run_parser = subparsers.add_parser(
        "dry-run",
        help="Resolve adapters and simulate trial lifecycle flow without real execution.",
    )
    dry_run_parser.add_argument("config", help="Path to a project YAML file.")
    dry_run_parser.add_argument(
        "--output-dir",
        help="Override the configured artifact root for this simulated run.",
    )
    dry_run_parser.set_defaults(handler=_handle_dry_run)

    benchmark_setup_parser = subparsers.add_parser(
        "benchmark-setup",
        help="Execute benchmark-owned environment setup/bootstrap through the platform runtime.",
    )
    benchmark_setup_parser.add_argument("config", help="Path to a project YAML file.")
    benchmark_setup_parser.add_argument(
        "--output-dir",
        help="Override the configured artifact root for this benchmark-side run.",
    )
    _add_device_override_arguments(benchmark_setup_parser)
    benchmark_setup_parser.set_defaults(handler=_handle_benchmark_setup)

    benchmark_run_parser = subparsers.add_parser(
        "benchmark-run",
        help="Execute benchmark-owned bootstrap/scoring without an external agent bridge.",
    )
    benchmark_run_parser.add_argument("config", help="Path to a project YAML file.")
    benchmark_run_parser.add_argument(
        "--output-dir",
        help="Override the configured artifact root for this benchmark-side run.",
    )
    _add_device_override_arguments(benchmark_run_parser)
    _add_runtime_override_arguments(benchmark_run_parser)
    benchmark_run_parser.set_defaults(handler=_handle_benchmark_run)

    registry_parser = subparsers.add_parser(
        "registry",
        help="List builtin adapters and registry metadata exposed by the platform.",
    )
    registry_parser.set_defaults(handler=_handle_registry_summary)
    registry_subparsers = registry_parser.add_subparsers(dest="registry_command")

    registry_summary_parser = registry_subparsers.add_parser(
        "summary",
        help="Print a summary of builtin agents, benchmarks, bridges, and scorers.",
    )
    registry_summary_parser.set_defaults(handler=_handle_registry_summary)

    registry_agent_parser = registry_subparsers.add_parser(
        "list-agents",
        help="List registered agent adapters.",
    )
    registry_agent_parser.add_argument(
        "--metadata",
        action="store_true",
        help="Include adapter metadata in the structured output.",
    )
    registry_agent_parser.set_defaults(handler=_handle_registry_list, registry_kind="agent")

    registry_benchmark_parser = registry_subparsers.add_parser(
        "list-benchmarks",
        help="List registered benchmark adapters.",
    )
    registry_benchmark_parser.add_argument(
        "--metadata",
        action="store_true",
        help="Include adapter metadata in the structured output.",
    )
    registry_benchmark_parser.set_defaults(
        handler=_handle_registry_list,
        registry_kind="benchmark",
    )

    registry_bridge_parser = registry_subparsers.add_parser(
        "list-bridges",
        help="List registered bridge adapters.",
    )
    registry_bridge_parser.add_argument(
        "--metadata",
        action="store_true",
        help="Include adapter metadata in the structured output.",
    )
    registry_bridge_parser.set_defaults(handler=_handle_registry_list, registry_kind="bridge")

    devices_parser = subparsers.add_parser(
        "devices",
        help="Inspect emulator backends, running Android devices, and health state.",
    )
    devices_subparsers = devices_parser.add_subparsers(dest="devices_command")

    devices_list_parser = devices_subparsers.add_parser(
        "list",
        help="List discovered emulator instances for the selected device mode.",
    )
    devices_list_parser.add_argument(
        "--config",
        required=True,
        help="Path to a project YAML file used for profile and backend defaults.",
    )
    _add_device_override_arguments(devices_list_parser, default_device_mode=DeviceMode.EXISTING_DEVICE.value)
    devices_list_parser.set_defaults(handler=_handle_devices_list)

    devices_health_parser = devices_subparsers.add_parser(
        "health-check",
        help="Run health checks for discovered emulator instances.",
    )
    devices_health_parser.add_argument(
        "--config",
        required=True,
        help="Path to a project YAML file used for profile and backend defaults.",
    )
    _add_device_override_arguments(devices_health_parser, default_device_mode=DeviceMode.EXISTING_DEVICE.value)
    devices_health_parser.set_defaults(handler=_handle_devices_health_check)

    worker_run_parser = subparsers.add_parser(
        "worker-run",
        help="Execute dummy trials through in-process/subprocess workers.",
    )
    worker_run_parser.add_argument("config", help="Path to a project YAML file.")
    worker_run_parser.set_defaults(handler=_handle_worker_run)

    emulator_demo_parser = subparsers.add_parser(
        "emulator-demo",
        help="Simulate fake emulator allocation, health checks, reset, and release flow.",
    )
    emulator_demo_parser.add_argument("config", help="Path to a project YAML file.")
    emulator_demo_parser.add_argument(
        "--device-count",
        type=int,
        default=2,
        help="Number of fake emulator instances to provision for the demo.",
    )
    emulator_demo_parser.set_defaults(handler=_handle_emulator_demo)

    run_parser = subparsers.add_parser(
        "run",
        help="Execute the configured platform pipeline and persist run artifacts.",
    )
    run_parser.add_argument("config", help="Path to a project YAML file.")
    run_parser.add_argument(
        "--output-dir",
        help="Override the configured artifact root for this run.",
    )
    _add_device_override_arguments(run_parser)
    _add_runtime_override_arguments(run_parser)
    _add_model_override_arguments(run_parser)
    run_parser.set_defaults(handler=_handle_run)

    summarize_parser = subparsers.add_parser(
        "summarize",
        help="Print the normalized summary for a run directory or summary.json file.",
    )
    summarize_parser.add_argument(
        "target",
        help="Path to a run directory or to summary.json.",
    )
    summarize_parser.set_defaults(handler=_handle_summarize)

    inspect_parser = subparsers.add_parser(
        "inspect-repo",
        help="Inspect a locally cloned third-party repository under references/.",
    )
    inspect_parser.add_argument("kind", choices=("agent", "benchmark"))
    inspect_parser.add_argument("repo_path", help="Path to the local repository checkout.")
    inspect_parser.set_defaults(handler=_handle_inspect_repo)

    scaffold_parser = subparsers.add_parser(
        "scaffold-adapter",
        help="Generate an adapter scaffold from a locally cloned third-party repository.",
    )
    scaffold_parser.add_argument("kind", choices=("agent", "benchmark"))
    scaffold_parser.add_argument("repo_path", help="Path to the local repository checkout.")
    scaffold_parser.add_argument("adapter_id", help="Adapter ID to place in the generated scaffold.")
    scaffold_parser.add_argument(
        "--output",
        help="Output path for the generated scaffold. Defaults under examples/integration/.",
    )
    scaffold_parser.set_defaults(handler=_handle_scaffold_adapter)

    checklist_parser = subparsers.add_parser(
        "integration-checklist",
        help="Generate a local integration checklist for a third-party repository.",
    )
    checklist_parser.add_argument("kind", choices=("agent", "benchmark"))
    checklist_parser.add_argument("repo_path", help="Path to the local repository checkout.")
    checklist_parser.add_argument(
        "--adapter-id",
        help="Optional adapter ID override for the checklist.",
    )
    checklist_parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Render the checklist as markdown or json.",
    )
    checklist_parser.set_defaults(handler=_handle_integration_checklist)

    benchmark_package_parser = subparsers.add_parser(
        "scaffold-benchmark-package",
        help="Generate a benchmark integration package scaffold from a local benchmark repo.",
    )
    benchmark_package_parser.add_argument("repo_path", help="Path to the local benchmark repository.")
    benchmark_package_parser.add_argument("adapter_id", help="Benchmark adapter ID to scaffold.")
    benchmark_package_parser.add_argument(
        "--output-dir",
        default="examples/integration",
        help="Directory under which the scaffold package will be created.",
    )
    benchmark_package_parser.add_argument(
        "--integration-mode",
        choices=("wrap", "native", "hybrid"),
        help="Override the suggested integration mode.",
    )
    benchmark_package_parser.set_defaults(handler=_handle_scaffold_benchmark_package)

    agent_package_parser = subparsers.add_parser(
        "scaffold-agent-package",
        help="Generate an agent integration package scaffold from a local agent repo.",
    )
    agent_package_parser.add_argument("repo_path", help="Path to the local agent repository.")
    agent_package_parser.add_argument("adapter_id", help="Agent adapter ID to scaffold.")
    agent_package_parser.add_argument(
        "--output-dir",
        default="examples/integration",
        help="Directory under which the scaffold package will be created.",
    )
    agent_package_parser.add_argument(
        "--integration-mode",
        choices=("wrap", "native", "hybrid"),
        help="Override the suggested integration mode.",
    )
    agent_package_parser.add_argument(
        "--capability-profile",
        choices=("auto", "text-only", "vision-capable"),
        default="auto",
        help="Override the inferred capability profile.",
    )
    agent_package_parser.set_defaults(handler=_handle_scaffold_agent_package)

    bridge_package_parser = subparsers.add_parser(
        "scaffold-bridge-package",
        help="Generate a pair-specific bridge package scaffold.",
    )
    bridge_package_parser.add_argument("bridge_id", help="Bridge adapter ID to scaffold.")
    bridge_package_parser.add_argument("--agent-id", required=True, help="Agent ID for this pair.")
    bridge_package_parser.add_argument(
        "--benchmark-id",
        required=True,
        help="Benchmark ID for this pair.",
    )
    bridge_package_parser.add_argument(
        "--output-dir",
        default="examples/integration",
        help="Directory under which the scaffold package will be created.",
    )
    bridge_package_parser.add_argument(
        "--integration-mode",
        choices=("wrap", "native", "hybrid"),
        default="wrap",
        help="Bridge integration mode to place in the scaffold.",
    )
    bridge_package_parser.add_argument(
        "--requires-pair-recipe",
        action="store_true",
        help="Mark the scaffold as requiring a pair-specific runtime recipe.",
    )
    bridge_package_parser.set_defaults(handler=_handle_scaffold_bridge_package)

    return parser


def _handle_validate(args: argparse.Namespace) -> int:
    spec = load_project_spec(Path(args.config))
    print(
        "Validated project "
        f"'{spec.project.name}' with {len(spec.agents)} agent(s), "
        f"{len(spec.benchmarks)} benchmark(s), and {len(spec.models)} model(s)."
    )
    print(json.dumps(spec.normalized_summary(), indent=2, sort_keys=True))
    return 0


def _handle_plan(args: argparse.Namespace) -> int:
    spec = load_project_spec(Path(args.config))
    registry = create_builtin_registry()
    planner = ExecutionPlanner(registry=registry)
    plan = planner.plan(spec)
    print(
        f"Planned run '{plan.run_id}' with {len(plan.planned_trials)} trial(s) and "
        f"{len(plan.diagnostics)} incompatible combination(s)."
    )
    print(json.dumps(plan.to_summary(), indent=2, sort_keys=True))
    return 0


def _handle_dry_run(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    spec = load_project_spec(config_path)
    registry = create_builtin_registry()
    planner = ExecutionPlanner(registry=registry)
    result = planner.dry_run(spec)
    store = ArtifactStore(output_root=Path(args.output_dir) if args.output_dir else None)
    layout = store.initialize_run(
        spec=spec,
        project_source=config_path,
        run_id=result.run_context.run_id,
        plan_payload=result.plan.to_summary(),
        summary_payload=store.build_summary_payload(result),
    )
    if spec.artifacts.persist_logs:
        configure_logging(args.verbose, log_file=layout.run_log_path)
    store.persist_simulated_run(layout=layout, spec=spec, plan=result.plan, result=result)
    print(
        f"Dry-run simulated {len(result.trial_states)} trial(s): "
        f"{result.scheduler_snapshot.succeeded} completed, "
        f"{result.scheduler_snapshot.failed} failed, "
        f"{result.scheduler_snapshot.retrying} retrying. "
        f"Artifacts: {layout.run_dir}"
    )
    print(json.dumps(result.to_summary(), indent=2, sort_keys=True))
    return 0


def _handle_registry_summary(args: argparse.Namespace) -> int:
    registry = create_builtin_registry()
    summary = registry.summary()
    print("Builtin registry summary.")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _handle_registry_list(args: argparse.Namespace) -> int:
    registry = create_builtin_registry()
    kind = args.registry_kind
    entries = registry.list_by_kind(kind)
    payload: dict[str, object] = {
        "kind": kind,
        "count": len(entries),
        "items": [entry.adapter_id for entry in entries],
    }
    if args.metadata:
        payload["metadata"] = [
            {
                "adapter_id": entry.adapter_id,
                "integration_mode": entry.metadata.integration_mode,
                "supported_modalities": list(entry.metadata.supported_modalities),
                "supported_backends": list(entry.metadata.supported_backends),
                "required_env": list(entry.metadata.required_env),
                "supported_benchmarks": list(entry.metadata.supported_benchmarks),
                "supported_model_protocols": list(entry.metadata.supported_model_protocols),
                "extra": dict(entry.metadata.extra),
            }
            for entry in entries
        ]
    noun = {
        "agent": "agent",
        "benchmark": "benchmark",
        "bridge": "bridge",
    }[kind]
    joined = ", ".join(entry.adapter_id for entry in entries) if entries else "(none)"
    print(f"Registered {noun} adapters ({len(entries)}): {joined}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _handle_devices_list(args: argparse.Namespace) -> int:
    spec = _load_spec_with_device_overrides(Path(args.config), args)
    pool, instances = _provision_device_pool(spec, instance_count=None)
    payload = {
        "device_mode": spec.devices.device_mode.value,
        "control_backend": spec.devices.control_backend,
        "default_profile": spec.devices.default_profile,
        "discovered": len(instances),
        "instances": [_instance_payload(instance) for instance in instances],
        "provider_events": [event.to_dict() for event in pool.provider_events()],
    }
    print(
        f"Discovered {len(instances)} device(s) in mode '{spec.devices.device_mode.value}' "
        f"for profile '{spec.devices.default_profile}'."
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _handle_devices_health_check(args: argparse.Namespace) -> int:
    spec = _load_spec_with_device_overrides(Path(args.config), args)
    pool, instances = _provision_device_pool(spec, instance_count=None)
    for instance in instances:
        pool.health_check(instance.instance_id)
    health_counts = {
        "healthy": sum(instance.health_status == HealthStatus.HEALTHY for instance in instances),
        "degraded": sum(instance.health_status == HealthStatus.DEGRADED for instance in instances),
        "unhealthy": sum(instance.health_status == HealthStatus.UNHEALTHY for instance in instances),
        "unknown": sum(instance.health_status == HealthStatus.UNKNOWN for instance in instances),
    }
    payload = {
        "device_mode": spec.devices.device_mode.value,
        "control_backend": spec.devices.control_backend,
        "default_profile": spec.devices.default_profile,
        "counts": health_counts,
        "instances": [_instance_payload(instance) for instance in instances],
        "provider_events": [event.to_dict() for event in pool.provider_events()],
    }
    print(
        f"Health-checked {len(instances)} device(s): "
        f"{health_counts['healthy']} healthy, "
        f"{health_counts['degraded']} degraded, "
        f"{health_counts['unhealthy']} unhealthy."
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _handle_worker_run(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    spec = load_project_spec(config_path)
    registry = create_builtin_registry()
    planner = ExecutionPlanner(registry=registry)
    plan = planner.plan(spec)
    orchestrator = TrialOrchestrator()
    result = orchestrator.run_plan(plan, retry_controller=RetryController(spec.retries))
    print(
        f"Worker run executed {len(result.worker_attempts)} worker attempt(s) across "
        f"{len(result.trial_states)} trial(s): "
        f"{result.scheduler_snapshot.succeeded} completed, "
        f"{result.scheduler_snapshot.failed} failed."
    )
    print(json.dumps(result.to_summary(), indent=2, sort_keys=True))
    return 0


def _handle_emulator_demo(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    spec = load_project_spec(config_path)
    registry = create_builtin_registry()
    planner = ExecutionPlanner(registry=registry)
    plan = planner.plan(spec)
    result = run_fake_emulator_demo(spec=spec, plan=plan, instance_count=args.device_count)
    print(
        f"Emulator demo provisioned {args.device_count} fake instance(s), "
        f"assigned {len(result.assignments)} trial(s), "
        f"queue_blocked_while_busy={result.queue_blocked_while_busy}."
    )
    print(json.dumps(result.to_summary(), indent=2, sort_keys=True))
    return 0


def _handle_benchmark_setup(args: argparse.Namespace) -> int:
    return _handle_benchmark_operation(args, operation="setup")


def _handle_benchmark_run(args: argparse.Namespace) -> int:
    return _handle_benchmark_operation(args, operation="probe")


def _resolve_run_directory(spec: object, output_dir: str | None) -> Path:
    if output_dir:
        return Path(output_dir)
    return Path(spec.artifacts.root_dir) / slugify(spec.project.run_name)


def _load_json_if_exists(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ArtifactError(f"failed to read artifact json: {path}") from error
    if not isinstance(payload, dict):
        raise ArtifactError(f"expected object json payload in: {path}")
    return payload


def _build_trial_summary_from_artifacts(
    *,
    trial_id: str,
    meta_payload: dict[str, object],
    score_payload: dict[str, object],
) -> dict[str, object]:
    spec_payload = meta_payload.get("spec", {})
    if not isinstance(spec_payload, dict):
        spec_payload = {}
    runtime_recipe = spec_payload.get("runtime_recipe", {})
    if not isinstance(runtime_recipe, dict):
        runtime_recipe = {}
    score_platform_metrics = score_payload.get("platform_metrics", {})
    if not isinstance(score_platform_metrics, dict):
        score_platform_metrics = {}
    meta_platform_metrics = meta_payload.get("platform_metrics", {})
    if not isinstance(meta_platform_metrics, dict):
        meta_platform_metrics = {}

    requested_modes: list[str] = []
    worker_mode = runtime_recipe.get("worker_mode")
    if worker_mode:
        requested_modes.append(str(worker_mode))

    execution_modes = meta_payload.get("execution_modes", [])
    if not isinstance(execution_modes, list):
        execution_modes = []
    instance_ids = meta_payload.get("instance_ids", [])
    if not isinstance(instance_ids, list):
        instance_ids = []
    reset_strategies = score_platform_metrics.get("reset_strategies", meta_platform_metrics.get("reset_strategies", []))
    if not isinstance(reset_strategies, list):
        reset_strategies = []

    return {
        "trial_id": trial_id,
        "task_id": meta_payload.get("task_id") or spec_payload.get("task_id") or trial_id,
        "agent_id": spec_payload.get("agent_id") or "",
        "benchmark_id": spec_payload.get("benchmark_id") or "",
        "status": meta_payload.get("status") or TrialStatus.PENDING.value,
        "attempt_count": int(meta_payload.get("attempt_count", 0) or 0),
        "total_duration_ms": int(
            score_platform_metrics.get("duration_ms", meta_platform_metrics.get("duration_ms", 0) or 0)
        ),
        "worker_attempts": int(
            score_platform_metrics.get("worker_attempts", meta_platform_metrics.get("worker_attempts", 0) or 0)
        ),
        "execution_modes": execution_modes,
        "requested_modes": requested_modes,
        "instance_ids": instance_ids,
        "reset_strategies": reset_strategies,
        "benchmark_seed_requested": bool(
            score_platform_metrics.get(
                "benchmark_seed_requested",
                meta_platform_metrics.get("benchmark_seed_requested", False),
            )
        ),
        "primary_metric": int(score_payload.get("primary_metric", 0) or 0),
        "platform_metrics": score_platform_metrics,
        "last_error_type": meta_payload.get("last_error_type"),
        "last_error_message": meta_payload.get("last_error_message"),
    }


def _load_existing_terminal_trial_summaries(layout: object) -> dict[str, dict[str, object]]:
    if not layout.trials_dir.exists():
        return {}
    summaries: dict[str, dict[str, object]] = {}
    for trial_dir in sorted(layout.trials_dir.iterdir()):
        if not trial_dir.is_dir():
            continue
        meta_payload = _load_json_if_exists(trial_dir / "meta.json")
        score_payload = _load_json_if_exists(trial_dir / "score.json")
        if meta_payload is None or score_payload is None:
            continue
        status = str(meta_payload.get("status", ""))
        if status not in _TERMINAL_TRIAL_STATUSES:
            continue
        summaries[trial_dir.name] = _build_trial_summary_from_artifacts(
            trial_id=trial_dir.name,
            meta_payload=meta_payload,
            score_payload=score_payload,
        )
    return summaries


def _should_reuse_terminal_trial_summary(summary: dict[str, object]) -> bool:
    status = str(summary.get("status", "") or "")
    return status in {
        TrialStatus.COMPLETED.value,
        TrialStatus.SKIPPED.value,
    }


def _merge_exact_status_counts(
    *,
    trial_summaries: dict[str, dict[str, object]],
    queued: int = 0,
    running: int = 0,
    retrying: int = 0,
) -> dict[str, int]:
    exact = {status.value: 0 for status in TrialStatus}
    for summary in trial_summaries.values():
        status = str(summary.get("status", ""))
        if status in exact:
            exact[status] += 1
    exact[TrialStatus.SCHEDULED.value] += queued
    exact[TrialStatus.RUNNING.value] += running
    exact[TrialStatus.RETRY_WAITING.value] += retrying
    return exact


def _derive_run_status(exact_status_counts: dict[str, int]) -> str:
    queued = exact_status_counts.get(TrialStatus.SCHEDULED.value, 0)
    running = (
        exact_status_counts.get(TrialStatus.PREPARING.value, 0)
        + exact_status_counts.get(TrialStatus.RUNNING.value, 0)
        + exact_status_counts.get(TrialStatus.SCORING.value, 0)
    )
    retrying = exact_status_counts.get(TrialStatus.RETRY_WAITING.value, 0)
    if exact_status_counts.get(TrialStatus.ABORTED.value, 0):
        return RunStatus.ABORTED.value
    if queued or running or retrying:
        return RunStatus.RUNNING.value
    if exact_status_counts.get(TrialStatus.FAILED.value, 0):
        return RunStatus.PARTIALLY_FAILED.value
    return RunStatus.COMPLETED.value


def _build_run_summary_payload(
    *,
    run_id: str,
    planned_trials: int,
    diagnostics: int,
    trial_summaries: dict[str, dict[str, object]],
    trial_order: tuple[str, ...],
    queued: int = 0,
    running: int = 0,
    retrying: int = 0,
    notes: list[str] | None = None,
    pool: dict[str, object] | None = None,
    status: str | None = None,
) -> dict[str, object]:
    exact = _merge_exact_status_counts(
        trial_summaries=trial_summaries,
        queued=queued,
        running=running,
        retrying=retrying,
    )
    resolved_status = status or _derive_run_status(exact)
    ordered_trials = [
        trial_summaries[trial_id]
        for trial_id in trial_order
        if trial_id in trial_summaries
    ]
    completed = exact[TrialStatus.COMPLETED.value]
    failed = exact[TrialStatus.FAILED.value]
    skipped = exact[TrialStatus.SKIPPED.value]
    aborted = exact[TrialStatus.ABORTED.value]
    total_duration_ms = sum(
        int(trial.get("total_duration_ms", 0) or 0)
        for trial in ordered_trials
    )
    success_rate = 0.0 if planned_trials == 0 else round(completed / planned_trials, 4)
    avg_trial_duration_ms = 0.0 if not ordered_trials else round(total_duration_ms / len(ordered_trials), 2)
    max_trial_duration_ms = max(
        (int(trial.get("total_duration_ms", 0) or 0) for trial in ordered_trials),
        default=0,
    )
    return {
        "run_id": run_id,
        "status": resolved_status,
        "counts": {
            "planned_trials": planned_trials,
            "diagnostics": diagnostics,
            "completed": completed,
            "failed": failed,
            "aborted": aborted,
            "retrying": retrying,
            "queued": queued,
            "running": running,
            "skipped": skipped,
        },
        "metrics_summary": {
            "success_rate": success_rate,
            "total_worker_attempts": sum(int(trial.get("worker_attempts", 0) or 0) for trial in ordered_trials),
            "avg_trial_duration_ms": avg_trial_duration_ms,
            "max_trial_duration_ms": max_trial_duration_ms,
        },
        "scheduler": {
            "queued": queued,
            "running": running,
            "succeeded": completed,
            "failed": failed,
            "skipped": skipped,
            "retrying": retrying,
            "exact_status_counts": exact,
        },
        "pool": pool or {},
        "trials": ordered_trials,
        "notes": notes or [],
    }


def _write_run_eval_results(
    *,
    store: ArtifactStore,
    layout: object,
    run_id: str,
    planned_trials: int,
    trial_entries: tuple[object, ...],
) -> None:
    default_agent_id = ""
    default_benchmark_id = ""
    if trial_entries:
        first_trial = trial_entries[0].trial
        default_agent_id = str(getattr(first_trial, "agent_id", "") or "")
        default_benchmark_id = str(getattr(first_trial, "benchmark_id", "") or "")
    try:
        payload = build_run_eval_results(
            Path(layout.run_dir),
            run_id=run_id,
            planned_trials=planned_trials,
            default_agent_id=default_agent_id,
            default_benchmark_id=default_benchmark_id,
            updated_at=_utcnow(),
        )
    except Exception as error:  # pragma: no cover - defensive logging path
        LOGGER.warning(
            "Failed to refresh eval_results.json for run '%s' under %s: %s",
            run_id,
            layout.run_dir,
            error,
        )
        return
    store.write_eval_results(layout, payload)


def _build_pending_plan(full_plan: object, *, spec: object, run_dir: Path, pending_entries: tuple[object, ...]) -> object:
    pending_context = RunContext(
        run_id=full_plan.run_id,
        project_snapshot=spec,
        artifact_root=run_dir,
    )
    pending_context.set_planned(planned_trials=len(pending_entries), diagnostics=len(full_plan.diagnostics))
    return replace(full_plan, run_context=pending_context, planned_trials=pending_entries)


def _handle_benchmark_operation(args: argparse.Namespace, *, operation: str) -> int:
    config_path = Path(args.config)
    spec = _load_spec_with_device_overrides(config_path, args)
    store = ArtifactStore()
    registry = create_builtin_registry()
    planner = ExecutionPlanner(registry=registry)
    retry_controller = RetryController(spec.retries)
    run_dir = _resolve_run_directory(spec, args.output_dir)
    run_id = run_dir.name
    plan = planner.plan(spec, run_id=run_id)
    if run_dir.exists():
        existing_contents = [path for path in run_dir.iterdir()]
        if existing_contents:
            raise ArtifactError(
                f"output directory already exists for benchmark-side execution: {run_dir}"
            )
    placeholder_summary = {
        "run": {
            "run_id": run_id,
            "status": RunStatus.CREATED.value,
            "planned_trials": plan.run_context.planned_trials,
            "diagnostics": plan.run_context.diagnostics,
        },
        "counts": {
            "planned_trials": plan.run_context.planned_trials,
            "diagnostics": plan.run_context.diagnostics,
            "completed": 0,
            "failed": 0,
            "retrying": 0,
            "queued": plan.run_context.planned_trials,
            "running": 0,
            "skipped": 0,
        },
        "metrics_summary": {
            "success_rate": 0.0,
            "total_worker_attempts": 0,
            "avg_trial_duration_ms": 0,
            "max_trial_duration_ms": 0,
        },
        "scheduler": {
            "queued": plan.run_context.planned_trials,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
            "retrying": 0,
            "exact_status_counts": {
                status.value: (plan.run_context.planned_trials if status == TrialStatus.SCHEDULED else 0)
                for status in TrialStatus
            },
        },
        "pool": {},
        "trials": [],
        "notes": [
            f"Benchmark-side operation '{operation}' initialized but has not finished yet."
        ],
    }
    layout = store.initialize_run_directory(
        spec=spec,
        project_source=config_path,
        run_dir=run_dir,
        run_id=run_id,
        plan_payload=plan.to_summary(),
        summary_payload=placeholder_summary,
    )
    if spec.artifacts.persist_logs:
        configure_logging(args.verbose, log_file=layout.run_log_path)
    orchestrator = TrialOrchestrator()
    result = orchestrator.run_benchmark_probe_pipeline(
        plan,
        spec=spec,
        registry=registry,
        retry_controller=retry_controller,
        run_layout=layout,
        operation=operation,
        device_count=spec.runtime.batch_size,
    )
    store.persist_platform_pipeline_run(
        layout=layout,
        spec=spec,
        plan=plan,
        result=result,
    )
    summary = store.build_platform_pipeline_summary_payload(result)
    noun = "Benchmark setup" if operation == "setup" else "Benchmark-side run"
    print(
        f"{noun} '{run_id}' completed with {summary['counts']['completed']} succeeded, "
        f"{summary['counts']['failed']} failed. Artifacts: {layout.run_dir}"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _handle_run(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    spec = _load_spec_with_device_overrides(config_path, args)
    store = ArtifactStore()
    registry = create_builtin_registry()
    planner = ExecutionPlanner(registry=registry)
    retry_controller = RetryController(spec.retries)
    run_dir = _resolve_run_directory(spec, args.output_dir)
    run_id = run_dir.name
    if spec.monitoring.cli_live_panel:
        print(
            f"[run] Initializing run '{run_id}' from {config_path}",
            flush=True,
        )
        print(f"[run] output_dir: {run_dir}", flush=True)
        print("[run] Loading config, registry, and retry policy...", flush=True)
        if any(benchmark.benchmark_id == "androidworld" for benchmark in spec.benchmarks):
            print(
                "[run] Expanding execution plan and discovering AndroidWorld tasks. "
                "This can take a while for full-suite runs before the emulator starts moving.",
                flush=True,
            )
        else:
            print("[run] Expanding execution plan...", flush=True)
    full_plan = planner.plan(spec, run_id=run_id)
    if spec.monitoring.cli_live_panel:
        print(
            f"[run] Plan ready: planned_trials={full_plan.run_context.planned_trials} "
            f"diagnostics={full_plan.run_context.diagnostics}",
            flush=True,
        )
    trial_order = tuple(entry.trial.trial_id for entry in full_plan.planned_trials)
    layout = store.build_run_layout(run_dir=run_dir, run_id=run_id)
    is_existing_run = (
        layout.manifest_path.exists()
        and layout.plan_path.exists()
        and layout.trials_dir.exists()
    )
    if not is_existing_run and run_dir.exists():
        existing_contents = [path for path in run_dir.iterdir()]
        if existing_contents:
            raise ArtifactError(
                f"output directory exists but is not a resumable snowl-mobile run: {run_dir}"
            )
    existing_terminal_summaries: dict[str, dict[str, object]] = {}
    if is_existing_run:
        existing_terminal_summaries = _load_existing_terminal_trial_summaries(layout)
    reusable_terminal_summaries = {
        trial_id: summary
        for trial_id, summary in existing_terminal_summaries.items()
        if _should_reuse_terminal_trial_summary(summary)
    }
    rerun_terminal_summaries = {
        trial_id: summary
        for trial_id, summary in existing_terminal_summaries.items()
        if not _should_reuse_terminal_trial_summary(summary)
    }
    pending_entries: list[object] = []
    for entry in full_plan.planned_trials:
        if entry.trial.trial_id in reusable_terminal_summaries:
            continue
        trial_dir = layout.trials_dir / entry.trial.trial_id
        if trial_dir.exists():
            store.clear_trial_directory(layout, entry.trial.trial_id)
        pending_entries.append(entry)

    if not is_existing_run:
        placeholder_summary = _build_run_summary_payload(
            run_id=run_id,
            planned_trials=full_plan.run_context.planned_trials,
            diagnostics=full_plan.run_context.diagnostics,
            trial_summaries={},
            trial_order=trial_order,
            queued=len(pending_entries),
            running=0,
            retrying=0,
            notes=[
                "Run initialized. Platform pipeline execution has not completed yet."
            ],
        )
        layout = store.initialize_run_directory(
            spec=spec,
            project_source=config_path,
            run_dir=run_dir,
            run_id=run_id,
            plan_payload=full_plan.to_summary(),
            summary_payload=placeholder_summary,
        )
        _write_run_eval_results(
            store=store,
            layout=layout,
            run_id=run_id,
            planned_trials=full_plan.run_context.planned_trials,
            trial_entries=tuple(full_plan.planned_trials),
        )
    if spec.artifacts.persist_logs:
        configure_logging(args.verbose, log_file=layout.run_log_path)
    store.write_project_snapshot(layout, config_path)
    store.write_plan(layout, full_plan.to_summary())
    if is_existing_run:
        LOGGER.info(
            "Resuming run '%s' from %s: completed_trials=%s pending_trials=%s rerun_trials=%s",
            run_id,
            layout.run_dir,
            len(reusable_terminal_summaries),
            len(pending_entries),
            len(rerun_terminal_summaries),
        )
        store.append_event(
            layout,
            {
                "event": "run_resumed",
                "run_id": run_id,
                "timestamp": _utcnow(),
                "completed_trials": len(reusable_terminal_summaries),
                "pending_trials": len(pending_entries),
                "rerun_trials": len(rerun_terminal_summaries),
            },
        )
        for trial_id in sorted(reusable_terminal_summaries):
            trial_layout = layout.trial_layout(trial_id)
            LOGGER.info(
                "Skipping completed trial '%s' using existing artifacts at %s",
                trial_id,
                trial_layout.trial_dir,
            )
            store.append_event(
                layout,
                {
                    "event": "trial_skipped_existing_result",
                    "run_id": run_id,
                    "trial_id": trial_id,
                    "timestamp": _utcnow(),
                    "trial_dir": str(trial_layout.trial_dir),
                },
            )
        for trial_id in sorted(rerun_terminal_summaries):
            LOGGER.info(
                "Re-running terminal trial '%s' because previous status was %s",
                trial_id,
                rerun_terminal_summaries[trial_id].get("status", ""),
            )
            store.append_event(
                layout,
                {
                    "event": "trial_rerun_scheduled",
                    "run_id": run_id,
                    "trial_id": trial_id,
                    "timestamp": _utcnow(),
                    "previous_status": rerun_terminal_summaries[trial_id].get("status", ""),
                },
            )
        progress_summary = _build_run_summary_payload(
            run_id=run_id,
            planned_trials=full_plan.run_context.planned_trials,
            diagnostics=full_plan.run_context.diagnostics,
            trial_summaries=dict(reusable_terminal_summaries),
            trial_order=trial_order,
            queued=len(pending_entries),
            running=0,
            retrying=0,
            notes=[
                "Run resumed. Existing successful trial artifacts were reused automatically; failed terminal trials were scheduled to run again."
            ],
        )
        store.write_summary(layout, progress_summary)
        _write_run_eval_results(
            store=store,
            layout=layout,
            run_id=run_id,
            planned_trials=full_plan.run_context.planned_trials,
            trial_entries=tuple(full_plan.planned_trials),
        )
        store.write_manifest(
            layout,
            store.build_manifest_payload(
                spec=spec,
                layout=layout,
                summary_payload=progress_summary,
            ),
        )
        if spec.monitoring.cli_live_panel:
            print(
                f"Resuming run '{run_id}' from {layout.run_dir}: "
                f"completed_trials={len(reusable_terminal_summaries)} "
                f"pending_trials={len(pending_entries)} "
                f"rerun_trials={len(rerun_terminal_summaries)}",
                flush=True,
            )

    if not pending_entries:
        final_summary = _build_run_summary_payload(
            run_id=run_id,
            planned_trials=full_plan.run_context.planned_trials,
            diagnostics=full_plan.run_context.diagnostics,
            trial_summaries=dict(reusable_terminal_summaries),
            trial_order=trial_order,
            notes=[
                "All planned trials already had terminal artifacts. No new execution was required."
            ],
        )
        store.write_summary(layout, final_summary)
        _write_run_eval_results(
            store=store,
            layout=layout,
            run_id=run_id,
            planned_trials=full_plan.run_context.planned_trials,
            trial_entries=tuple(full_plan.planned_trials),
        )
        store.write_manifest(
            layout,
            store.build_manifest_payload(
                spec=spec,
                layout=layout,
                summary_payload=final_summary,
            ),
        )
        print(
            f"Run '{run_id}' completed with {final_summary['counts']['completed']} succeeded, "
            f"{final_summary['counts']['failed']} failed, "
            f"{full_plan.run_context.planned_trials} total trial(s) using device_mode='{spec.devices.device_mode.value}'. "
            f"Artifacts: {layout.run_dir}"
        )
        print(f"Summary: {layout.summary_path}")
        return 0

    orchestrator = TrialOrchestrator()
    pending_plan = _build_pending_plan(
        full_plan,
        spec=spec,
        run_dir=run_dir,
        pending_entries=tuple(pending_entries),
    )
    persisted_trial_summaries: dict[str, dict[str, object]] = dict(reusable_terminal_summaries)

    def _persist_completed_trial(trial_state: object, trial_summary: object, trial_artifact: object) -> None:
        store.persist_platform_trial_artifacts(
            layout=layout,
            spec=spec,
            trial_state=trial_state,
            trial_summary=trial_summary,
            trial_artifact=trial_artifact,
        )
        persisted_trial_summaries[trial_summary.trial_id] = trial_summary.to_dict()
        store.append_event(
            layout,
            {
                "event": "trial_finished",
                "run_id": run_id,
                "trial_id": trial_summary.trial_id,
                "timestamp": _utcnow(),
                "status": trial_summary.status,
                "duration_ms": trial_summary.total_duration_ms,
                "primary_metric": trial_summary.primary_metric,
            },
        )
        progress_summary = _build_run_summary_payload(
            run_id=run_id,
            planned_trials=full_plan.run_context.planned_trials,
            diagnostics=full_plan.run_context.diagnostics,
            trial_summaries=persisted_trial_summaries,
            trial_order=trial_order,
            queued=pending_plan.run_context.queued,
            running=pending_plan.run_context.running,
            retrying=pending_plan.run_context.retrying,
            notes=[
                "Run in progress. Completed trial artifacts are persisted incrementally."
            ],
        )
        store.write_summary(layout, progress_summary)
        _write_run_eval_results(
            store=store,
            layout=layout,
            run_id=run_id,
            planned_trials=full_plan.run_context.planned_trials,
            trial_entries=tuple(full_plan.planned_trials),
        )
        store.write_manifest(
            layout,
            store.build_manifest_payload(
                spec=spec,
                layout=layout,
                summary_payload=progress_summary,
            ),
        )

    def _emit_trial_progress(event: dict[str, object]) -> None:
        event_name = str(event.get("event", "") or "")
        current_index = event.get("current_index", "?")
        total_trials = event.get("total_trials", "?")
        trial_id = str(event.get("trial_id", "") or "")
        if event_name == "trial_started":
            instruction = str(event.get("instruction", "") or "").strip()
            instruction_display = instruction if instruction else "<empty instruction>"
            store.append_event(
                layout,
                {
                    "event": "trial_started",
                    "run_id": run_id,
                    "trial_id": trial_id,
                    "timestamp": _utcnow(),
                    "current_index": current_index,
                    "total_trials": total_trials,
                    "attempt": event.get("attempt", 0),
                    "device": str(event.get("device", "") or ""),
                    "instance_id": str(event.get("instance_id", "") or ""),
                    "console_port": event.get("console_port"),
                    "grpc_port": event.get("grpc_port"),
                    "appium_port": event.get("appium_port"),
                    "avd_name": str(event.get("avd_name", "") or ""),
                    "instruction": instruction,
                },
            )
            if not spec.monitoring.cli_live_panel:
                return
            print(
                f"[run] Task {current_index}/{total_trials} started: {trial_id}",
                flush=True,
            )
            print(f"[run] instruction: {instruction_display}", flush=True)
            print(f"[run] device: {str(event.get('device', '') or '<unknown>')}", flush=True)
            return
        if not spec.monitoring.cli_live_panel:
            return
        if event_name == "trial_finished":
            print(
                "[run] Task "
                f"{current_index}/{total_trials} finished: {trial_id} "
                f"status={str(event.get('status', ''))} "
                f"completed={event.get('completed', 0)} "
                f"failed={event.get('failed', 0)} "
                f"aborted={event.get('aborted', 0)} "
                f"skipped={event.get('skipped', 0)}",
                flush=True,
            )

    result = orchestrator.run_platform_pipeline(
        pending_plan,
        spec=spec,
        registry=registry,
        retry_controller=retry_controller,
        run_layout=layout,
        device_count=spec.runtime.batch_size,
        trial_persist_callback=_persist_completed_trial,
        trial_progress_callback=_emit_trial_progress,
        trial_progress_index={
            entry.trial.trial_id: index
            for index, entry in enumerate(full_plan.planned_trials, start=1)
        },
        total_planned_trials=full_plan.run_context.planned_trials,
    )
    merged_trial_summaries = dict(reusable_terminal_summaries)
    merged_trial_summaries.update(
        {summary.trial_id: summary.to_dict() for summary in result.trial_summaries}
    )
    exact_counts = _merge_exact_status_counts(trial_summaries=reusable_terminal_summaries)
    for status, count in result.scheduler_snapshot.exact_status_counts.items():
        exact_counts[status] = exact_counts.get(status, 0) + count
    final_summary = _build_run_summary_payload(
        run_id=run_id,
        planned_trials=full_plan.run_context.planned_trials,
        diagnostics=full_plan.run_context.diagnostics,
        trial_summaries=merged_trial_summaries,
        trial_order=trial_order,
        queued=exact_counts[TrialStatus.SCHEDULED.value],
        running=(
            exact_counts[TrialStatus.PREPARING.value]
            + exact_counts[TrialStatus.RUNNING.value]
            + exact_counts[TrialStatus.SCORING.value]
        ),
        retrying=exact_counts[TrialStatus.RETRY_WAITING.value],
        notes=list(dict.fromkeys(result.notes)) or [
            "Executed platform pipeline with pair-aware bridge resolution."
        ],
        pool=result.pool_snapshot,
        status=_derive_run_status(exact_counts),
    )
    store.write_plan(layout, full_plan.to_summary())
    store.write_summary(layout, final_summary)
    _write_run_eval_results(
        store=store,
        layout=layout,
        run_id=run_id,
        planned_trials=full_plan.run_context.planned_trials,
        trial_entries=tuple(full_plan.planned_trials),
    )
    store.write_manifest(
        layout,
        store.build_manifest_payload(
            spec=spec,
            layout=layout,
            summary_payload=final_summary,
        ),
    )
    store.append_event(
        layout,
        {
            "event": "run_completed" if final_summary["status"] != RunStatus.ABORTED.value else "run_aborted",
            "run_id": run_id,
            "timestamp": result.finished_at,
            "status": final_summary["status"],
            "total_duration_ms": result.total_duration_ms,
        },
    )
    LOGGER.info(
        "Completed platform pipeline run '%s' at %s with %s completed and %s failed trial(s)",
        run_id,
        layout.run_dir,
        final_summary["counts"]["completed"],
        final_summary["counts"]["failed"],
    )
    print(
        f"Run '{run_id}' completed with {final_summary['counts']['completed']} succeeded, "
        f"{final_summary['counts']['failed']} failed, "
        f"{full_plan.run_context.planned_trials} total trial(s) using device_mode='{spec.devices.device_mode.value}'. "
        f"Artifacts: {layout.run_dir}"
    )
    print(f"Summary: {layout.summary_path}")
    return 0


def _handle_summarize(args: argparse.Namespace) -> int:
    target = Path(args.target)
    summary_path = target if target.name == "summary.json" else target / "summary.json"
    if not summary_path.exists():
        raise ArtifactError(f"summary file not found: {summary_path}")
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ArtifactError(f"failed to parse summary json: {summary_path}") from error

    counts = payload.get("counts", {})
    metrics = payload.get("metrics_summary", {})
    print(
        f"Summary for run '{payload.get('run_id', summary_path.parent.name)}': "
        f"{counts.get('completed', 0)} completed, "
        f"{counts.get('failed', 0)} failed, "
        f"success_rate={metrics.get('success_rate', 0)}."
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _handle_inspect_repo(args: argparse.Namespace) -> int:
    if args.kind == "benchmark":
        inspection = BenchmarkRepositoryInspector().inspect(Path(args.repo_path))
    elif args.kind == "agent":
        inspection = AgentRepositoryInspector().inspect(Path(args.repo_path))
    else:
        inspection = RepositoryInspector().inspect(Path(args.repo_path), repo_kind=args.kind)
    print(json.dumps(inspection.to_dict(), indent=2, sort_keys=True))
    return 0


def _handle_scaffold_adapter(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo_path)
    inspection = RepositoryInspector().inspect(repo_path, repo_kind=args.kind)
    output_path = (
        Path(args.output)
        if args.output
        else Path("examples/integration") / f"{args.adapter_id}_{args.kind}_adapter.py"
    )
    result = AdapterScaffoldGenerator().generate(
        ScaffoldRequest(
            repo_kind=args.kind,
            adapter_id=args.adapter_id,
            inspection=inspection,
            output_path=output_path,
        )
    )
    print(
        f"Generated {args.kind} scaffold '{result.class_name}' at {result.output_path}"
    )
    return 0


def _handle_integration_checklist(args: argparse.Namespace) -> int:
    if args.kind == "benchmark":
        inspection = BenchmarkRepositoryInspector().inspect(Path(args.repo_path))
        checklist = BenchmarkIntegrationChecklistGenerator().generate(
            inspection,
            adapter_id=args.adapter_id,
        )
    elif args.kind == "agent":
        inspection = AgentRepositoryInspector().inspect(Path(args.repo_path))
        checklist = AgentIntegrationChecklistGenerator().generate(
            inspection,
            adapter_id=args.adapter_id,
        )
    else:
        inspection = RepositoryInspector().inspect(Path(args.repo_path), repo_kind=args.kind)
        checklist = IntegrationChecklistGenerator().generate(
            inspection,
            adapter_id=args.adapter_id,
        )
    if args.format == "json":
        print(json.dumps(checklist.to_dict(), indent=2, sort_keys=True))
    else:
        print(checklist.to_markdown())
    return 0


def _handle_scaffold_benchmark_package(args: argparse.Namespace) -> int:
    inspection = BenchmarkRepositoryInspector().inspect(Path(args.repo_path))
    result = BenchmarkPackageScaffoldGenerator().generate(
        BenchmarkPackageScaffoldRequest(
            adapter_id=args.adapter_id,
            inspection=inspection,
            output_dir=Path(args.output_dir),
            integration_mode=args.integration_mode,
        )
    )
    print(
        f"Generated benchmark package scaffold at {result.scaffold_root} "
        f"with {len(result.generated_files)} file(s)"
    )
    return 0


def _handle_scaffold_agent_package(args: argparse.Namespace) -> int:
    inspection = AgentRepositoryInspector().inspect(Path(args.repo_path))
    result = AgentPackageScaffoldGenerator().generate(
        AgentPackageScaffoldRequest(
            adapter_id=args.adapter_id,
            inspection=inspection,
            output_dir=Path(args.output_dir),
            integration_mode=args.integration_mode,
            capability_profile=args.capability_profile,
        )
    )
    print(
        f"Generated agent package scaffold at {result.scaffold_root} "
        f"with {len(result.generated_files)} file(s)"
    )
    return 0


def _handle_scaffold_bridge_package(args: argparse.Namespace) -> int:
    result = BridgePackageScaffoldGenerator().generate(
        BridgePackageScaffoldRequest(
            bridge_id=args.bridge_id,
            agent_id=args.agent_id,
            benchmark_id=args.benchmark_id,
            output_dir=Path(args.output_dir),
            integration_mode=args.integration_mode,
            requires_pair_recipe=args.requires_pair_recipe,
        )
    )
    print(
        f"Generated bridge package scaffold at {result.scaffold_root} "
        f"with {len(result.generated_files)} file(s)"
    )
    return 0


def _apply_cli_env_overrides(args: argparse.Namespace) -> None:
    env_overrides = {
        "PHONE_AGENT_MODEL": getattr(args, "model_name", None),
        "PHONE_AGENT_BASE_URL": getattr(args, "base_url", None),
        "PHONE_AGENT_API_KEY": getattr(args, "api_key", None),
    }
    for name, value in env_overrides.items():
        if value is None:
            continue
        resolved = str(value).strip()
        if resolved:
            os.environ[name] = resolved


def _apply_platform_env_defaults() -> None:
    resolver_specs = (
        ("OPEN_AUTOGLM_HOME", "snowl_mobile.adapters.agents.open_autoglm", "resolve_open_autoglm_repo_path"),
        ("MOBILE_AGENT_E_HOME", "snowl_mobile.adapters.agents.mobile_agent_e", "resolve_mobile_agent_e_repo_path"),
        ("MOBILE_AGENT_V3_5_HOME", "snowl_mobile.adapters.agents.mobile_agent_v3_5", "resolve_mobile_agent_v3_5_repo_path"),
        ("MOBILE_SAFETY_HOME", "snowl_mobile.adapters.benchmarks.mobilesafetybench", "resolve_mobilesafetybench_repo_path"),
        ("ANDROID_WORLD_HOME", "snowl_mobile.adapters.benchmarks.androidworld", "resolve_androidworld_repo_path"),
    )
    for env_name, module_name, resolver_name in resolver_specs:
        try:
            module = __import__(module_name, fromlist=[resolver_name])
            resolver = getattr(module, resolver_name)
            resolved = resolver()
        except Exception:
            continue
        os.environ[env_name] = str(resolved)
    if not os.environ.get("APPIUM_BIN", "").strip():
        resolved_appium = shutil.which("appium")
        if resolved_appium:
            os.environ["APPIUM_BIN"] = resolved_appium


def _load_spec_with_device_overrides(config_path: Path, args: argparse.Namespace):
    spec = load_project_spec(config_path)
    device_mode_raw = getattr(args, "device_mode", None)
    adb_serials_raw = getattr(args, "adb_serials", None)
    avd_names_raw = getattr(args, "avd_names", None)
    batch_size_raw = getattr(args, "batch_size", None)
    max_steps_raw = getattr(args, "max_steps", None)
    model_name_raw = getattr(args, "model_name", None)
    if (
        device_mode_raw is None
        and not adb_serials_raw
        and not avd_names_raw
        and batch_size_raw is None
        and max_steps_raw is None
        and model_name_raw is None
    ):
        return spec

    devices = replace(
        spec.devices,
        device_mode=spec.devices.device_mode if device_mode_raw is None else DeviceMode(device_mode_raw),
        adb_serials=spec.devices.adb_serials if not adb_serials_raw else tuple(adb_serials_raw),
        avd_names=spec.devices.avd_names if not avd_names_raw else tuple(avd_names_raw),
    )
    runtime = replace(
        spec.runtime,
        batch_size=spec.runtime.batch_size if batch_size_raw is None else max(1, int(batch_size_raw)),
        max_steps=spec.runtime.max_steps if max_steps_raw is None else max(1, int(max_steps_raw)),
    )

    models = spec.models
    agents = spec.agents
    if model_name_raw is not None:
        model_name = str(model_name_raw).strip()
        if model_name:
            if len(spec.models) != 1:
                raise ArtifactError(
                    "--model-name currently supports run configs with exactly one model entry."
                )
            original_model_id = spec.models[0].model_id
            models = (replace(spec.models[0], model_id=model_name),)
            agents = tuple(
                replace(agent, model_ref=model_name if agent.model_ref == original_model_id else agent.model_ref)
                for agent in spec.agents
            )

    return replace(spec, devices=devices, runtime=runtime, models=models, agents=agents)


def _provision_device_pool(spec, *, instance_count: int | None):
    profile = next(
        profile
        for profile in spec.devices.emulator_profiles
        if profile.profile_id == spec.devices.default_profile
    )
    pool = create_emulator_pool_manager(
        device_mode=spec.devices.device_mode,
        adb_serials=spec.devices.adb_serials,
        avd_names=spec.devices.avd_names,
    )
    return pool, pool.provision_pool(profile=profile, instance_count=instance_count)


def _instance_payload(instance) -> dict[str, object]:
    return {
        "instance_id": instance.instance_id,
        "adb_serial": instance.adb_serial,
        "appium_port": instance.appium_port,
        "grpc_port": instance.grpc_port,
        "avd_name": instance.avd_name,
        "snapshot_name": instance.snapshot_name,
        "status": instance.status.value,
        "current_trial_id": instance.current_trial_id,
        "last_heartbeat_at": instance.last_heartbeat_at,
        "health_status": instance.health_status.value,
        "profile_id": instance.profile_id,
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0

    try:
        _apply_cli_env_overrides(args)
        _apply_platform_env_defaults()
        return handler(args)
    except SnowlMobileError as error:
        LOGGER.error("%s", error)
        print(f"error: {error}", file=sys.stderr)
        return 1


__all__ = ["build_parser", "main"]
