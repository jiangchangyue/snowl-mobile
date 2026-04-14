from __future__ import annotations

from dataclasses import dataclass

from snowl_mobile.core.agent_spec import AgentSpec
from snowl_mobile.core.benchmark_spec import BenchmarkSpec
from snowl_mobile.core.registry import Registry
from snowl_mobile.core.runtime_recipe import RuntimeRecipe
from snowl_mobile.models.model_spec import ModelSpec


@dataclass(frozen=True, slots=True)
class CompatibilityIssue:
    scope: str
    message: str


@dataclass(frozen=True, slots=True)
class CompatibilityReport:
    scope: str
    subject: str
    compatible: bool
    issues: tuple[CompatibilityIssue, ...] = ()
    notes: tuple[str, ...] = ()
    bridge_id: str = ""
    pair_recipe_id: str = ""

    def render(self) -> str:
        if self.compatible:
            details: list[str] = ["compatible"]
            if self.bridge_id:
                details.append(f"via bridge '{self.bridge_id}'")
            if self.pair_recipe_id:
                details.append(f"pair recipe '{self.pair_recipe_id}' applied")
            if self.notes:
                details.append("; ".join(self.notes))
            return f"{self.scope}: {' - '.join(details)}"
        details = "; ".join(issue.message for issue in self.issues)
        return f"{self.scope}: incompatible - {details}"


@dataclass(slots=True)
class CompatibilityResolver:
    registry: Registry | None = None

    def check_agent_model(self, agent: AgentSpec, model: ModelSpec) -> CompatibilityReport:
        issues = tuple(
            CompatibilityIssue(scope="agent_model", message=message)
            for message in agent.model_compatibility_issues(model)
        )
        return CompatibilityReport(
            scope="agent_model",
            subject=f"{agent.variant_id} x {model.model_id}",
            compatible=not issues,
            issues=issues,
        )

    def check_agent_benchmark(
        self,
        agent: AgentSpec,
        benchmark: BenchmarkSpec,
        runtime_recipe: RuntimeRecipe | None = None,
    ) -> CompatibilityReport:
        messages = list(agent.benchmark_compatibility_issues(benchmark))
        if agent.supported_benchmarks and benchmark.benchmark_id not in agent.supported_benchmarks:
            messages.append(
                f"agent '{agent.agent_id}' does not list benchmark '{benchmark.benchmark_id}' as supported"
            )
        bridge = self._resolve_bridge(agent.agent_id, benchmark.benchmark_id)
        bridge_id = "" if bridge is None else bridge.adapter_id
        pair_recipe_id = "" if runtime_recipe is None else runtime_recipe.pair_recipe_id
        notes: list[str] = []

        if runtime_recipe is not None and runtime_recipe.bridge_id and runtime_recipe.bridge_id != bridge_id:
            messages.append(
                f"runtime recipe requests bridge '{runtime_recipe.bridge_id}' but registry did not resolve that pair bridge"
            )

        if messages and bridge is not None:
            if bridge.requires_pair_recipe and not pair_recipe_id:
                messages.append(
                    f"bridge '{bridge.adapter_id}' requires a pair-specific runtime recipe but none matched"
                )
            else:
                notes.append(
                    f"direct incompatibilities are expected to be handled by bridge '{bridge.adapter_id}'"
                )
                notes.extend(f"direct issue: {message}" for message in messages)
                messages = []
        elif runtime_recipe is not None and runtime_recipe.bridge_id:
            if bridge is None:
                messages.append(
                    f"runtime recipe references bridge '{runtime_recipe.bridge_id}' but no bridge is registered for this pair"
                )
            else:
                notes.append(f"pair-specific bridge '{bridge.adapter_id}' selected for this combination")
                if bridge.requires_pair_recipe and not pair_recipe_id:
                    messages.append(
                        f"bridge '{bridge.adapter_id}' requires a pair-specific runtime recipe but none matched"
                    )

        issues = tuple(CompatibilityIssue(scope="agent_benchmark", message=message) for message in messages)
        return CompatibilityReport(
            scope="agent_benchmark",
            subject=f"{agent.variant_id} x {benchmark.benchmark_id}",
            compatible=not issues,
            issues=issues,
            notes=tuple(notes),
            bridge_id=bridge_id,
            pair_recipe_id=pair_recipe_id,
        )

    def check_benchmark_runtime(
        self, benchmark: BenchmarkSpec, runtime_recipe: RuntimeRecipe
    ) -> CompatibilityReport:
        messages: list[str] = []
        notes: list[str] = []
        if runtime_recipe.control_backend != benchmark.device_backend:
            messages.append(
                f"runtime control_backend '{runtime_recipe.control_backend}' does not match benchmark device_backend '{benchmark.device_backend}'"
            )
        if benchmark.device_backend not in runtime_recipe.backend_requirements:
            messages.append(
                f"runtime backend_requirements does not include '{benchmark.device_backend}'"
            )
        if runtime_recipe.reset_policy != benchmark.reset_policy:
            messages.append(
                f"runtime reset_policy '{runtime_recipe.reset_policy}' does not match benchmark reset_policy '{benchmark.reset_policy}'"
            )
        missing_env = set(benchmark.required_env) - set(runtime_recipe.required_env)
        if missing_env:
            missing = ", ".join(sorted(missing_env))
            messages.append(f"runtime required_env is missing benchmark env vars: {missing}")
        if runtime_recipe.pair_recipe_id:
            notes.append(f"pair runtime recipe '{runtime_recipe.pair_recipe_id}' overrides the default runtime shell")
        if runtime_recipe.bridge_id:
            notes.append(f"bridge '{runtime_recipe.bridge_id}' is attached to this runtime recipe")
        issues = tuple(
            CompatibilityIssue(scope="benchmark_runtime", message=message)
            for message in messages
        )
        return CompatibilityReport(
            scope="benchmark_runtime",
            subject=f"{benchmark.benchmark_id} x {runtime_recipe.device_profile}",
            compatible=not issues,
            issues=issues,
            notes=tuple(notes),
            bridge_id=runtime_recipe.bridge_id,
            pair_recipe_id=runtime_recipe.pair_recipe_id,
        )

    def check_agent_runtime(self, agent: AgentSpec, runtime_recipe: RuntimeRecipe) -> CompatibilityReport:
        messages: list[str] = []
        if agent.supported_backends and runtime_recipe.control_backend not in agent.supported_backends:
            messages.append(
                f"runtime control_backend '{runtime_recipe.control_backend}' is not in agent supported_backends"
            )
        missing_env = set(agent.required_env) - set(runtime_recipe.required_env)
        if missing_env:
            missing = ", ".join(sorted(missing_env))
            messages.append(f"runtime required_env is missing agent env vars: {missing}")
        issues = tuple(
            CompatibilityIssue(scope="agent_runtime", message=message)
            for message in messages
        )
        return CompatibilityReport(
            scope="agent_runtime",
            subject=f"{agent.variant_id} x {runtime_recipe.control_backend}",
            compatible=not issues,
            issues=issues,
            bridge_id=runtime_recipe.bridge_id,
            pair_recipe_id=runtime_recipe.pair_recipe_id,
        )

    def aggregate(
        self,
        *,
        agent: AgentSpec,
        model: ModelSpec,
        benchmark: BenchmarkSpec,
        runtime_recipe: RuntimeRecipe,
    ) -> tuple[CompatibilityReport, ...]:
        return (
            self.check_agent_model(agent, model),
            self.check_agent_benchmark(agent, benchmark, runtime_recipe),
            self.check_agent_runtime(agent, runtime_recipe),
            self.check_benchmark_runtime(benchmark, runtime_recipe),
        )

    def collect_issues(self, reports: tuple[CompatibilityReport, ...]) -> list[str]:
        messages: list[str] = []
        for report in reports:
            if not report.compatible:
                messages.extend(issue.message for issue in report.issues)
        return messages

    def _resolve_bridge(self, agent_id: str, benchmark_id: str) -> "_BridgeResolution | None":
        if self.registry is None:
            return None
        entry = self.registry.resolve_bridge_for_pair(agent_id, benchmark_id)
        if entry is None:
            return None
        bridge = self.registry.instantiate_bridge(entry.adapter_id)
        contract = bridge.describe_bridge()
        return _BridgeResolution(
            adapter_id=entry.adapter_id,
            requires_pair_recipe=contract.requires_pair_recipe,
        )


@dataclass(frozen=True, slots=True)
class _BridgeResolution:
    adapter_id: str
    requires_pair_recipe: bool
