# Adaptive Agent Harness V1 Implementation Plan

> **For agentic workers:** implement task-by-task with fresh review checkpoints and tests before production behavior.

**Goal:** Build a clone-ready Adaptive Agent Harness with LITE, PRO, and FACTORY profiles, prebuilt agents, subscription-first Claude/Codex adapters, adaptive tool/environment/project discovery, Guardian enforcement, evidence-backed loops, and deterministic completion.

**Architecture:** A Python 3.11+ CLI owns orchestration and durable state. Agents are provider-neutral manifests plus provider adapters; the same agent identities can execute through Claude Code or Codex CLI. Projects are adapted through a Project Adapter that detects existing stack, commands, environment variable names, local tools, rules, and risks without persisting secret values. LITE preserves the Santiago Planner → Generator → Evaluator pattern; PRO and FACTORY compose additional roles over the same artifact protocol.

**Tech Stack:** Python 3.11+, stdlib, PyYAML, Git CLI, optional Claude Code CLI, optional Codex CLI, optional Docker/Playwright/security tools. No GitHub Actions.

## Global Constraints

- Subscription-first; API credentials are never required and API fallback is disabled by default.
- `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are removed from provider child-process environments in subscription-only mode.
- Existing projects are inspected before modification and their current conventions/rules take precedence over generic defaults.
- `.env*` secret values are never persisted in AAH artifacts; only variable names and classifications may be stored.
- Producer and evaluator are always independent executions. `UNVERIFIED` never counts as `PASS`.
- Final completion is decided by deterministic code, not an agent claim.
- LITE stays sequential and intentionally close to `santmun/claude-code-harness`.
- No `.github/workflows/*` files.

---

### Task 1: Package, configuration, artifacts, and state

**Files:** `pyproject.toml`, `factory/__init__.py`, `factory/models.py`, `factory/config.py`, `factory/artifacts.py`, `factory/state.py`, `tests/test_core.py`.

- [ ] Write tests for run creation, JSON/JSONL artifacts, local config defaults, and state transitions.
- [ ] Run tests and verify failure before implementation.
- [ ] Implement typed enums/dataclasses, artifact store, run IDs, and atomic state persistence.
- [ ] Run tests to green.

### Task 2: Project, environment, provider, model, and tool adaptation

**Files:** `factory/project_adapter.py`, `factory/envs.py`, `factory/tools.py`, `factory/providers.py`, `factory/router.py`, `tests/test_discovery.py`, `tests/test_router.py`.

- [ ] Test detection of Python/Node/Docker/Git projects, existing instructions, `.env` variable names, tools, Claude/Codex availability, and subscription-only environment sanitization.
- [ ] Verify tests fail.
- [ ] Implement Project Adapter manifests, Env Router, Tool Router, provider probes/adapters, and model/capability routing.
- [ ] Verify tests pass.

### Task 3: Guardian, evidence, progress, and deterministic Final Gate

**Files:** `factory/guardian.py`, `factory/evidence.py`, `factory/progress.py`, `factory/final_gate.py`, `tests/test_guardian.py`, `tests/test_final_gate.py`.

- [ ] Test OPEN/GUARDED/LOCKED command decisions, protected paths, secret redaction, evidence validation, no-progress detection, and PASS/FAIL/UNVERIFIED gate rules.
- [ ] Verify red state.
- [ ] Implement minimal policy engine and deterministic final gate.
- [ ] Verify green state.

### Task 4: Prebuilt agent identities and provider-neutral executor

**Files:** `agents/*.yaml`, `factory/agents.py`, `factory/executor.py`, `.claude/agents/aah-*.md`, `.claude/skills/aah/SKILL.md`, `AGENTS.md`, `tests/test_agents.py`.

- [ ] Test every required role has identity, mission, capability, tools, artifact contracts, and independence rules.
- [ ] Implement agent registry and prompt compiler.
- [ ] Implement Claude execution using `claude -p` with role-specific tool restrictions and Codex execution using `codex exec` with sandbox/output controls.
- [ ] Add native Claude bridge files and Codex project guidance without requiring either provider.
- [ ] Verify tests.

### Task 5: LITE profile

**Files:** `factory/profiles/lite.py`, `profiles/lite.yaml`, `tests/test_lite.py`.

- [ ] Create fake-provider E2E test proving Planner → Builder → independent Evaluator → Findings → Fix → fresh Evaluator → Final Gate.
- [ ] Verify failing baseline.
- [ ] Implement bounded loop, stable finding IDs, evidence ingestion, resume checkpoints, and escalation signal.
- [ ] Verify LITE E2E green.

### Task 6: PRO profile

**Files:** `factory/profiles/pro.py`, `profiles/pro.yaml`, `tests/test_pro.py`.

- [ ] Test Planner → Architect → Builder → Tester → Evaluator → Fixer loop and LITE→PRO escalation inputs.
- [ ] Implement PRO orchestration, technical test evidence, fresh evaluator passes, and progress detector behavior.
- [ ] Verify green.

### Task 7: FACTORY profile and task graph

**Files:** `factory/taskgraph.py`, `factory/profiles/factory.py`, `profiles/factory.yaml`, `tests/test_factory.py`.

- [ ] Test DAG validation, dependency ordering, task-level LITE/PRO selection, integration gate, and PRO→FACTORY escalation signals.
- [ ] Implement task scheduler with safe sequential fallback and optional isolated parallel execution hooks.
- [ ] Implement Integrator/System Tester/Security Reviewer/Final Reviewer stages.
- [ ] Verify green.

### Task 8: CLI, installer, existing-project integration, and domain packs

**Files:** `factory/cli.py`, `install.sh`, `factory/domains.py`, `README.md`, `.gitignore`, `examples/*`, `tests/test_cli.py`, `tests/test_project_integration.py`.

- [ ] Test `setup`, `doctor`, `run`, `status`, `resume`, `eval`, `fix`, `report`, `rollback`, and project adaptation.
- [ ] Implement install flow that creates a virtualenv, installs AAH, detects an existing target repo, preserves its files, installs only uniquely named provider bridge files, and stores local state outside tracked secrets.
- [ ] Implement code/content/research/operations domain templates over the same loop protocol.
- [ ] Verify full test suite locally with fake providers and no network/API requirement.
- [ ] Confirm no GitHub Actions exist.

### Task 9: Release verification

- [ ] Run the complete unit/integration suite.
- [ ] Run CLI help and doctor smoke tests.
- [ ] Run LITE, PRO, and FACTORY fake-provider fixtures end-to-end.
- [ ] Inspect repository for accidentally committed secrets and `.github/workflows`.
- [ ] Verify installer syntax with `bash -n install.sh`.
- [ ] Commit the verified implementation to the build branch and integrate to `main` only after verification.
