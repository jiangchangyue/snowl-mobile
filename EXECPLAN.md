# EXECPLAN.md

This document is the living execution log for implementation work in `snowl-mobile`. It complements [CODEX-IMPLEMENTATION-ROADMAP.md](./CODEX-IMPLEMENTATION-ROADMAP.md) by tracking current status, near-term focus, risks, and design decisions.

## Phase Ledger

The repository is tracking two views at once:

- the roadmap phases in [CODEX-IMPLEMENTATION-ROADMAP.md](./CODEX-IMPLEMENTATION-ROADMAP.md);
- the finer-grained implementation increments requested during repository bring-up.

| Roadmap Phase | Increment | Goal | Status |
| --- | --- | --- | --- |
| Phase 0 | P0 | Repository bootstrap, package skeleton, CLI/config/artifact foundations | Completed |
| Phase 0 | P1 | Unified config schema, core specs, and policy contracts | Completed |
| Phase 0 | P2 | Adapter abstractions, plugin registry, compatibility dry-run | Completed |
| Phase 1 | P3 | Execution planning, trial lifecycle state machine, and scheduler skeleton | Completed |
| Phase 1 | P4 | Run directory normalization, artifact store, logs, and trajectory persistence | Completed |
| Phase 2 | P5 | Worker isolation, subprocess transport, and host/worker execution shell | Completed |
| Phase 1 | P6 | Emulator pool abstraction, reset strategy framework, and slot-aware scheduling skeleton | Completed |
| Phase 2 | P7 | CLI main flow and end-to-end dummy pipeline | Completed |
| Phase 3 | P8 | Third-party integration toolkit, references convention, and local scaffolding workflow | Completed |
| Phase 3 | P9 | Benchmark integration scaffold, contract hardening, and validation workflow | Completed |
| Phase 3 | P10 | Agent integration scaffold, capability declaration, and validation workflow | Completed |
| Phase 2 | P11 | Bridge contract, pair-specific runtime recipe, and pair scaffold workflow | Completed |
| Phase 3 | P12 | Final user workflow, copy-paste prompts, readiness checklist, and future integration examples | Completed |
| Phase 3 | P13 | First real benchmark integration via MobileSafetyBench wrap-first hybrid adapter | Completed |
| Phase 3 | P14 | First real agent integration via Open-AutoGLM wrap-first hybrid adapter | Completed |
| Phase 2 | P15 | Real Android emulator backend with existing-device discovery, health checks, and lease flow | Completed |
| Phase 3 | P16 | First real pair integration via Open-AutoGLM x MobileSafetyBench minimal bridge-backed run | Completed |
| Phase 2 | Next | Runtime bridge expansion and environment-specific worker backends | Not started |
| Phase 3 | Pending | Wrap-mode real integrations | Not started |
| Phase 4 | Pending | Monitoring and aggregation | Not started |
| Phase 5 | Pending | Native adapters and cleanup | Not started |
| Phase 6 | Pending | Dynamic safety task synthesis | Not started |

## Current Focus

### Completed foundation work

- create the `src/snowl_mobile/` package layout;
- establish minimal config loading and schema foundations;
- harden the central contract layer around `ProjectSpec`, `AgentSpec`, `BenchmarkSpec`, `ModelSpec`, `RuntimeRecipe`, `RetryPolicy`, `ResetPolicy`, and `ArtifactPolicy`;
- add adapter base classes, registry-backed discovery, compatibility diagnostics, and builtin dry-run stubs;
- add `ExecutionPlanner`, `TrialStateMachine`, `RunContext`, `RetryController`, and an in-memory `Scheduler` skeleton;
- expose `plan` and simulated `dry-run` CLI flows that expand trial matrices and exercise retryable state transitions with dummy adapters;
- normalize run and trial artifact layout through `ArtifactStore`, including `manifest.json`, `plan.json`, `summary.json`, `events.jsonl`, `trajectory.json`, run logs, and trial logs;
- add `WorkerSpec`, `WorkerLauncher`, JSON-lines `WorkerTransport`, `WorkerResult`, and a minimal `TrialOrchestrator` that runs dummy trials through in-process or subprocess workers;
- add `EmulatorPoolManager`, `EmulatorLease`, `HealthStatus`, `ResetManager`, a fake emulator provider, and scheduler support for slot-aware dispatch;
- connect the CLI `run` path end to end so config loading, registry lookup, compatibility checks, planning, fake emulator allocation, worker execution, reset bookkeeping, and artifact persistence now execute as one dummy pipeline;
- add `summarize` so persisted `summary.json` files can be read back as a normalized run report;
- fix the local third-party repo convention around `references/agents/<repo_name>/` and `references/benchmarks/<repo_name>/`, with Codex explicitly working from user-managed local clones;
- add a generic integration toolkit with repo inspection, adapter scaffold generation, integration checklist generation, and mock reference repos for future manual-clone workflows;
- add benchmark-specific inspection, contract validation, and a package scaffold that emits adapter/register/config/test/docs/contract artifacts in one shot;
- add agent-specific inspection, capability declaration validation, and a package scaffold that emits adapter/register/capability/config/test/docs/contract artifacts in one shot;
- add bridge contracts, pair-specific runtime recipe schema, bridge-aware compatibility diagnostics, and a bridge package scaffold for future pair debugging;
- add final user-facing prompt docs, readiness checklist, and future integration example configs so the first real manual-clone workflow is operational;
- land the first real benchmark integration for `MobileSafetyBench`, including task discovery from the upstream manifest, wrap-first hybrid contract mapping, a minimal integration config, and mock wrapped-task validation;
- land the first real agent integration for `Open-AutoGLM`, including real repo inspection, capability/model-binding mapping, backend-aware compatibility checks, and mock wrapped-agent validation;
- land the first real Android emulator backend for `existing_device` mode, including `adb` discovery, health checks, lease/release flow, CLI device inspection commands, and run-time device mode overrides;
- land the first real pair integration for `Open-AutoGLM x MobileSafetyBench`, including a pair-specific bridge, a minimal real-run config, a bridge-aware `run` path, pair-native trajectory/score persistence, and fake-device smoke coverage for the bridge path;
- add a repository-level CLI entrypoint;
- add a registry shell and run artifact scaffolding;
- create stdlib-only verification commands and tests;
- record implementation decisions for the next phase.

### Still explicitly out of scope

- real emulator scheduling, reset orchestration, or worker IPC;
- real scoring logic or web monitoring;
- heavy dependency installation.

## Current Status Snapshot

- repository scaffold created under `src/snowl_mobile/`;
- minimal CLI now supports `validate-config`, `plan`, simulated `dry-run`, end-to-end dummy `run`, and `summarize`;
- contract-first spec modules now validate cross-field compatibility for agents, models, benchmarks, devices, and policies;
- adapter abstractions, builtin registry registration, and dry-run planning now resolve dummy adapters by string ID and emit readable compatibility reports;
- trial planning now produces stable `run_id` and `trial_id` values and records initial `TrialSpec` entries before scheduling;
- the scheduler layer is currently single-process and in-memory, but it already tracks `queued`, `running`, `succeeded`, `failed`, `skipped`, and `retrying` counters from exact trial statuses;
- dry-run execution now persists dummy run artifacts and stub trajectory step payloads under a stable on-disk layout;
- runtime recipes now map to worker execution shells, with `in_process` kept local and `venv/container` funneled through a subprocess launcher;
- the host engine can now execute builtin dummy trials through a real host/worker boundary and retry retryable worker failures;
- emulator slots are now modeled explicitly, and the scheduler can hold queued trials until a compatible fake device lease becomes available;
- the default example now expands to multiple benchmark tasks and multiple trials, and a completed dummy run persists aggregate metrics plus per-trial duration/attempt data into `summary.json`;
- future third-party integrations now have stable local docs and tooling: the user clones into `references/`, Codex inspects the local checkout, generates a scaffold, and then wires registry/config/test updates;
- benchmark integrations now have a stronger product path: benchmark repo inspection -> contract/checklist -> package scaffold -> local validation, still without touching any real upstream benchmark in this phase;
- the first real benchmark integration is now present for `MobileSafetyBench`, but it intentionally stops at task discovery, contract mapping, minimal config wiring, and mock wrapped execution rather than full emulator-backed runtime;
- the first real agent integration is now present for `Open-AutoGLM`, but it intentionally stops at capability/model-binding mapping, compatibility enforcement, minimal config wiring, and mock wrapped execution rather than full device-backed runtime;
- the emulator backend now supports real `existing_device` discovery through `adb`, while `managed_avd` remains an explicit contract boundary with fail-fast behavior instead of full automatic lifecycle control;
- the platform `run` path is no longer dummy-only: when a registered bridge exposes a concrete pair execution path, `run` can execute that bridge through the same config/plan/artifact/summary flow;
- the first real pair config now exists at `configs/runs/autoglm_mobilesafetybench_minimal.yml`, with `batch_size=1`, `existing_device`, one selected task, and explicit pair recipe / bridge selection;
- agent integrations now have a stronger product path: agent repo inspection -> capability/contract/checklist -> package scaffold -> local validation, still without touching any real upstream agent in this phase;
- pair-specific integrations now have a stronger product path: bridge contract -> pair runtime recipe -> planner diagnostics -> scaffold package, still without touching any real pair runtime in this phase;
- user-facing real-integration workflow is now documented end to end: clone -> prompt -> scaffold/implementation -> validate/plan/dry-run;
- unittest-based smoke coverage validates imports, config parsing, registry lookup, compatibility reporting, planning, state-machine transitions, retry behavior, artifact persistence, logging bootstrap, and CLI output.

## Next Phase

The next increment should finish the remaining runtime work around real bridges and stronger isolation:

- grow the subprocess shell into pluggable `venv` / `conda` / `container` worker backends without changing the host-side worker contract.
- attach the new device lease/reset skeleton to a fuller `TrialOrchestrator` run path with richer benchmark hooks.
- begin separating the dummy benchmark/agent execution shell from future wrap/native bridge implementations so real upstream repos can plug in without changing the CLI contract.
- use the new integration toolkit against the first real local checkouts under `references/agents/` and `references/benchmarks/`, keeping wrap-first boundaries explicit.
- start applying the benchmark scaffold package against the first real local benchmark checkout once the user intentionally provides one under `references/benchmarks/`.
- expand the new `existing_device` backend into fuller `managed_avd`, snapshot restore, and Appium session management when the dependency boundary is ready.

## Risks

- The current YAML loader is intentionally stdlib-only. It now supports the repository example config and empty inline mappings, but it is still a constrained subset and should eventually be replaced or wrapped by a fuller YAML implementation once dependency policy is settled.
- Builtin adapters are intentionally dry-run stubs; they validate contracts and planning flow only.
- The scheduler is intentionally single-process and memory-backed. It defines the orchestration surface, but not real concurrency or device binding yet.
- Screenshot and XML step artifacts are currently stub files produced by simulated dry-run export, not real device captures.
- The subprocess worker currently reuses the host Python interpreter and environment; it defines the isolation protocol first, not a full dependency-isolated runtime yet.
- The emulator pool now supports real `existing_device` discovery and health checks, but `managed_avd` start/stop, snapshot restore reliability, and Appium session bootstrapping are still incomplete.
- The first real pair path currently executes in-process through a bridge. It is enough for the first unified closure, but it is not yet an isolated worker-backed runtime.
- Placeholder modules are present for contract stability, but most runtime-facing classes are intentionally non-functional until later phases.
- The integration toolkit only inspects local repository structure and generates scaffolds/checklists in this phase; it does not auto-implement a real third-party adapter end to end.
- The `MobileSafetyBench` adapter currently uses a wrap-first hybrid path: task discovery and metric mapping are real, but the wrapped execution entry is still mocked until the runtime/orchestrator can host a real upstream environment loop.
- The new benchmark scaffold package is still a TODO-rich template; it productizes how to integrate a benchmark, but it does not execute real benchmark logic yet.
- The new agent scaffold package is still a TODO-rich template; it productizes how to integrate an agent, but it does not execute real agent logic yet.
- The new bridge scaffold package is still a TODO-rich template; it productizes how to integrate a pair-specific bridge, but it does not execute real pair runtime logic yet.
- The new prompt docs and readiness checklist encode the current platform structure, but they still assume Codex will fill real adapter logic only after the user intentionally provides a local checkout.

## Decision Log

- 2026-03-16: Adopted `src/` layout to match repository bootstrap guidance and prevent accidental root imports during tests.
- 2026-03-16: Kept the Phase 0 toolchain stdlib-only so validation and tests do not depend on network access.
- 2026-03-16: Added stub modules for future phases now to stabilize import paths and contract names early.
- 2026-03-16: Kept the contract layer on frozen stdlib dataclasses instead of introducing `pydantic` yet, so the core schema remains lightweight, explicit, and install-free in the current environment.
- 2026-03-16: Split implementation tracking into `P1-contracts` and `P1-runtime` to preserve the roadmap ordering while recording the user-requested contract-hardening increment separately.
- 2026-03-16: Added registry-managed builtin dummy adapters and a dry-run planner so future third-party integrations can plug into a stable discovery and compatibility surface before runtime execution exists.
- 2026-03-16: Kept the trial lifecycle richer than the public queue counters by modeling `PENDING`, `SCHEDULED`, `PREPARING`, `RUNNING`, `SCORING`, `COMPLETED`, `FAILED`, `RETRY_WAITING`, `SKIPPED`, and `ABORTED` as exact internal states.
- 2026-03-16: Implemented the first scheduler as a single-process, in-memory queue so planning, retry, and lifecycle semantics can stabilize before emulator or worker complexity is introduced.
- 2026-03-16: Standardized the simulated run layout early so later real integrations can write into stable `run/` and `trial/` artifact paths without revisiting core filenames.
- 2026-03-16: Mapped `WorkerMode.IN_PROCESS` directly to in-process execution and treated `venv/container` as subprocess-backed shells for now, so future environment-specific launchers can land without changing `RuntimeRecipe`.
- 2026-03-16: Treated emulator slots as schedulable leases instead of ambient global state, so device binding can remain explicit when real emulator backends arrive.
- 2026-03-16: Kept `run` focused on a fully dummy but end-to-end pipeline first, so the CLI contract and artifact expectations stabilize before real third-party integrations arrive.
- 2026-03-16: Fixed the default third-party workflow around user-managed local clones under `references/` so future Codex-assisted integrations can stay offline by default and auditable from stable paths.
- 2026-03-17: Split third-party integration tooling into benchmark-specific and agent-specific product paths so future real repo integrations can reuse templates, contracts, and validation instead of bespoke glue code.
- 2026-03-17: Moved direct agent-benchmark compatibility decisions out of pure config validation and into planner-time compatibility resolution so future bridge-based pairs can be diagnosed instead of rejected too early.
- 2026-03-17: Added copy-paste prompt docs and readiness checks so the first real manual-clone integration can start from a stable, documented workflow instead of ad hoc instructions.
- 2026-03-17: Landed `MobileSafetyBench` as the first real benchmark integration using a wrap-first hybrid adapter so the platform can validate a real upstream task manifest and scoring contract before taking on full emulator-backed execution.
- 2026-03-17: Landed `Open-AutoGLM` as the first real agent integration using a wrap-first hybrid adapter so the platform can validate a real upstream model/action/device contract before taking on full device-backed execution.
- 2026-03-17: Upgraded the emulator backend from fake-only to a dual-mode shell where `existing_device` performs real `adb` discovery and health checks first, while `managed_avd` remains a deliberate, explicit future lifecycle boundary.
- 2026-03-17: Added the first pair-specific real bridge for `Open-AutoGLM x MobileSafetyBench` because the agent and benchmark disagree on who owns action execution; the bridge keeps MobileSafetyBench in charge of reset/observation/scoring while keeping Open-AutoGLM in charge of model inference and device actions.
