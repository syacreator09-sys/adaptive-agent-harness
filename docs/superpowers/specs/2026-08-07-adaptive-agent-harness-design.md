# Adaptive Agent Harness — Design Specification

**Date:** 2026-08-07  
**Repository:** `syacreator09-sys/adaptive-agent-harness`  
**Product name:** Adaptive Agent Harness (AAH)  
**Status:** Approved design baseline for implementation

## 1. Goal

Build a reusable, subscription-first, multi-agent harness that can autonomously plan, produce, independently verify, repair, re-verify, and finish work only when evidence proves the requested result is complete.

AAH must support three execution profiles — **LITE**, **PRO**, and **FACTORY** — without requiring API keys, while adapting to the CLIs, subscriptions, models, and tools available on each cloned machine.

The harness is a runtime. Systems such as Factory V5, Hermes, content factories, research workflows, and future projects consume this runtime rather than duplicating its orchestration logic.

## 2. Core principle

The agent that produces work must not be allowed to approve its own work.

Every profile follows the same protocol:

`REQUEST → SPEC → PRODUCE → VERIFY → FINDINGS → FIX → RE-VERIFY → FINAL GATE`

A verbal statement such as “done”, “looks good”, or “everything works” is never sufficient evidence.

A requirement can only be:

- `PASS`: verified with admissible evidence.
- `FAIL`: verified failure with evidence.
- `UNVERIFIED`: not proven. This never counts as pass.

The final completion decision is deterministic and independent from agent opinion.

## 3. Design heritage: LITE and the Santiago harness

LITE deliberately preserves the strengths of `santmun/claude-code-harness`:

- fresh agents with no shared conversational context;
- coordination through persistent files;
- Planner separate from Generator;
- Generator separate from Evaluator;
- a closed `SPEC` with a binary rubric;
- Git used as checkpoint/memory;
- findings with stable IDs;
- bounded fix/evaluate loops;
- sequential hand-off to avoid environment contamination.

AAH will not turn LITE into a heavy factory. LITE is the smallest reliable profile and remains conceptually close to the original Planner → Generator → Evaluator loop.

If implementation reuses substantial source text or code from the MIT-licensed reference repository, the required MIT attribution will be preserved.

## 4. Execution profiles

### 4.1 LITE

Purpose: small features, scripts, fixes, prototypes, individual content artifacts, and low-complexity tasks.

Flow:

`Planner → Producer → Evaluator → [Fix → fresh Evaluator]* → Final Gate`

Characteristics:

- sequential by default;
- fresh sessions;
- minimal state;
- maximum three verification passes by default;
- no Architect unless escalation occurs;
- no unnecessary parallelism;
- evidence required for every rubric item;
- escalation to PRO when repeated failure or architectural complexity is detected.

### 4.2 PRO

Purpose: complete applications, APIs, service integrations, agents, medium/high-complexity automations, and changes involving multiple modules.

Flow:

`Planner → Architect → Builder → Tester → Evaluator → [Fixer → Tester → fresh Evaluator]* → Final Gate`

Responsibilities are deliberately distinct:

- **Builder** creates the implementation.
- **Tester** executes technical checks: build, typecheck, lint, unit, integration, API, browser, and other configured tests.
- **Evaluator** judges whether the delivered system satisfies the product/specification rubric.
- **Fixer** repairs only explicit findings and cannot silently expand scope.

PRO may escalate to FACTORY when the task decomposes into multiple independent workstreams or cross-service integration becomes the primary challenge.

### 4.3 FACTORY

Purpose: large systems, multi-service projects, Hermes-scale work, platform construction, large content programs, or tasks that benefit from decomposition and controlled parallelism.

Flow:

`Router → Planner → Architect → Task Graph → Workers → Integrator → System Tester → Evaluator → Security/Quality Gates → Reviewer → Final Gate`

FACTORY is not “use the strongest model everywhere”. It is an orchestration mode.

The Architect produces a DAG/task graph. Each task may internally run using LITE or PRO depending on its complexity and risk. Independent tasks may run in isolated worktrees/sandboxes. Dependent tasks remain sequential.

The Integrator must merge and validate outputs before the system-level evaluator can approve the overall project.

## 5. Complexity and risk are separate axes

AAH evaluates two independent dimensions:

- `complexity_score: 0..100`
- `risk_score: 0..100`

Default profile mapping:

- complexity 0–25: LITE
- complexity 26–70: PRO
- complexity 71–100: FACTORY

Risk does not automatically determine complexity. A small production authentication change may be low complexity and high risk.

Risk affects Guardian mode and required gates.

## 6. Guardian modes

Guardian is an enforcement layer, not another developer agent.

### OPEN

For prototypes and low-risk local work.

- logs all operations;
- allows normal development freely;
- blocks universal destructive actions;
- warns on suspicious scope/dependency/security behavior.

### GUARDED

Default for most work.

- allows normal code creation, tests, builds, package management, browser automation, and project-local Docker operations;
- protects secrets and critical configuration;
- enforces scope and Git boundaries;
- blocks or escalates high-risk destructive commands;
- detects suspicious dependencies and production access.

### LOCKED

For production, infrastructure, customer data, payments, auth, migrations, and other sensitive work.

- strict allowlists for sensitive operations;
- isolated worktrees/sandboxes when supported;
- human gates for irreversible or production-changing actions;
- stronger network/filesystem restrictions;
- security gates mandatory before completion.

Universal destructive actions remain blocked even in OPEN unless an explicit policy allows them.

## 7. Subscription-first provider architecture

AAH must work without API keys.

Provider modes:

- `claude_only`
- `codex_only`
- `dual`

At setup, the harness probes local capabilities instead of assuming availability.

Detection includes:

- CLI installed;
- authenticated session available;
- supported execution modes;
- usable model aliases/capabilities;
- Git;
- Docker;
- Playwright/browser tooling;
- language runtimes and package managers;
- optional security/testing tools.

Default billing policy:

`subscription_only`

AAH must not silently fall back to paid API usage.

API adapters may exist later but are disabled unless explicitly enabled by the operator.

Provider authentication remains owned by the provider CLI. AAH does not copy OAuth tokens into project files, prompts, logs, or Git.

## 8. Model routing

Agents declare required capabilities, not permanent model names.

Examples:

- `deep_reasoning`
- `strong_coding`
- `fast_verification`
- `independent_review`
- `security_review`
- `low_cost_routine`

The Model Router resolves capabilities against what exists on the current machine and the selected policy:

- `quality`
- `balanced`
- `economy`

Manual per-agent model/provider overrides are supported through machine-local configuration.

When both Claude and Codex are available, cross-provider verification is preferred when useful:

- Codex build → Claude evaluate
- Claude build → Codex evaluate

When only one provider is available, independence is preserved through fresh contexts/sessions and restricted inputs.

## 9. Setup and machine-local configuration

The same repository must clone cleanly onto different machines.

First-run flow:

`clone → factory setup → capability probes → short wizard → factory.local.yaml → doctor → ready`

The setup wizard asks only:

1. provider strategy: Claude / Codex / both / auto;
2. subscription-only billing confirmation, default yes;
3. quality policy: quality / balanced / economy;
4. default execution profile: auto / lite / pro / factory;
5. Guardian policy: auto / open / guarded / locked.

`factory.local.yaml` is ignored by Git and stores machine-specific choices, never provider secrets.

## 10. Persistent run state

Every run receives a stable ID.

Example artifact layout:

```text
.aah/
└── runs/
    └── RUN-20260807-001/
        ├── REQUEST.json
        ├── SPEC.md
        ├── RUBRIC.json
        ├── ARCHITECTURE.md
        ├── TASKS.json
        ├── STATE.json
        ├── FINDINGS.json
        ├── EVIDENCE.jsonl
        ├── FINAL_REPORT.md
        ├── logs/
        ├── screenshots/
        └── artifacts/
```

State records at minimum:

- run ID;
- domain;
- selected profile;
- Guardian mode;
- provider/model assignments;
- current phase;
- pass count;
- rubric totals;
- findings;
- Git base/current commits;
- task graph state;
- timestamps;
- failure/retry information.

Runs must support pause, process failure, machine restart, and resume without relying on conversation history.

## 11. Artifact protocol

Agents coordinate through typed artifacts, not direct conversations.

Minimum contracts:

### REQUEST

Normalized user intent, constraints, domain, risk hints, and operator overrides.

### SPEC

Closed definition of requested outcome, scope, exclusions, assumptions, user flows, interfaces, and technical decisions required for execution.

### RUBRIC

Machine-readable binary criteria with evidence requirements.

### FINDINGS

Stable IDs (`F-001`, `F-002`, …), severity, rubric linkage, reproduction/evidence, status, and verification history.

### EVIDENCE

Append-only records pointing to actual command results, tests, HTTP outputs, screenshots, files, traces, or other domain-specific proof.

### FINAL_REPORT

Completed requirements, unresolved minors if allowed, selected providers/models, passes, changed files/commits, evidence summary, startup/use instructions, and final gate result.

## 12. Progress detector and automatic escalation

AAH must detect unproductive loops.

Signals include:

- rubric score change;
- findings resolved;
- new findings introduced;
- regressions;
- identical/repeated finding IDs;
- relevant diff activity;
- test movement;
- repeated agent/provider failure.

Default behavior:

1. normal repair attempt;
2. change repair strategy/model/session when available;
3. architectural re-diagnosis;
4. escalate LITE → PRO or PRO → FACTORY when objective rules are met;
5. request a human decision only when the remaining blocker is genuinely non-resolvable without product/production authority.

AAH must not continue unlimited loops merely because `max_loops` has not been reached.

## 13. Final Gate

The Final Gate is deterministic code.

Agents cannot set `DONE=true`.

For a run to complete, configured mandatory conditions must be satisfied, including:

- every required rubric criterion is PASS;
- zero unverified required criteria;
- zero open critical findings;
- zero open major findings unless an explicit policy permits them;
- mandatory tests/build/security gates pass;
- required evidence exists and references valid artifacts;
- integration/system verification passes for FACTORY.

If the conditions are false, the run remains incomplete regardless of agent claims.

## 14. Tool registry

Tools are capabilities assigned per role and domain.

Code capabilities may include:

- Git
- shell
- language runtimes
- package managers
- Docker
- browser/Playwright
- HTTP client
- database tools
- security scanners

Content capabilities may include:

- image generation/editing
- video generation/rendering
- voice
- subtitles
- FFmpeg
- metadata validation

Research capabilities may include:

- web/search
- browser
- files
- citation validation

Operations capabilities may include project-authorized integrations.

An agent receives only the capabilities necessary for its assigned task.

## 15. Domain packs

The first production-quality domain is `code`.

After the core is stable, the same runtime supports additional domain packs.

### Content

`Strategist → Producer → independent Content Evaluator → Findings → Revision → QA → Final Gate`

Possible rubric evidence:

- aspect ratio;
- resolution;
- duration;
- hook constraints;
- subtitle presence;
- spelling;
- safe zones;
- audio properties;
- brand constraints;
- factual claim verification;
- CTA requirements.

### Research

`Research Planner → Researchers → Evidence Collector → Fact Checker → Contradiction Reviewer → Synthesis → Citation Gate`

### Operations

`Planner → Builder → Simulator/Dry Run → Evaluator → Production Gate`

Production actions remain governed by Guardian policies.

## 16. Hermes integration

Hermes consumes AAH as an external runtime/CLI.

Conceptual flow:

`Hermes → AAH CLI → capability discovery → profile/router → execution loop → structured result`

Hermes does not need to store provider OAuth tokens or API keys for AAH when local authenticated CLIs are used.

## 17. CLI contract

Minimum intended commands:

- `factory setup`
- `factory doctor`
- `factory run`
- `factory status`
- `factory resume`
- `factory eval`
- `factory fix`
- `factory report`
- `factory rollback`

Explicit profile flags:

- `--profile auto`
- `--profile lite`
- `--profile pro`
- `--profile factory`

Explicit Guardian flags:

- `--guardian auto`
- `--guardian open`
- `--guardian guarded`
- `--guardian locked`

## 18. Git and isolation

Git is the canonical checkpoint layer for code-domain runs.

AAH records base and resulting commits per phase.

LITE remains sequential and can operate in the main checkout when safe.

PRO may use isolated worktrees for risky changes or when independent verification requires a protected environment.

FACTORY uses isolated worktrees/sandboxes for parallel independent tasks by default where supported.

No two workers may concurrently modify the same checkout.

Rollback must restore to an explicit recorded checkpoint; destructive reset commands are not issued casually by an agent.

## 19. Security boundaries

AAH must protect at least:

- `.env*`
- `.git/`
- `.claude/`
- `.codex/`
- AAH internal state/configuration
- SSH credentials
- cloud credentials
- package registry credentials
- secrets present in logs/output
- production databases and infrastructure

Sensitive provider/runtime directories may be inspected only through narrowly scoped probes required for capability detection and never copied into artifacts.

Logs redact recognized secrets before persistence.

## 20. No GitHub Actions

This repository will not use GitHub Actions.

Testing and release verification are executed locally through the repository CLI/scripts and provider agents. CI adapters may be designed as optional future extensions, but no `.github/workflows/*` implementation is part of this project unless explicitly requested later.

## 21. Testing strategy

AAH itself must be tested as aggressively as the projects it evaluates.

Test layers:

- unit tests for routing, state, policy, schemas, evidence validation, and final gate;
- integration tests for provider adapters using deterministic fake CLIs;
- filesystem/Git fixture repositories;
- intentionally broken sample projects;
- LITE end-to-end fixtures;
- PRO repair/escalation fixtures;
- FACTORY DAG/integration fixtures;
- crash/resume fixtures;
- Guardian policy fixtures;
- secret redaction fixtures;
- provider-unavailable and rate-limit/failure fixtures.

No provider subscription is required for the default automated test suite; fake deterministic provider processes cover orchestration logic.

Real-provider smoke tests remain opt-in local tests.

## 22. Benchmark against the reference LITE harness

Before claiming LITE is an improvement, AAH will include a reproducible benchmark specification comparing equivalent tasks against the conceptual reference behavior.

Metrics include:

- rubric completion;
- false PASS rate;
- findings detected;
- regressions introduced;
- verification passes;
- recoverability;
- evidence completeness;
- wall time when measurable.

If an added mechanism makes LITE less reliable, it must be simplified or removed rather than retained for architectural elegance.

## 23. Implementation sequence

Implementation is intentionally staged.

### Milestone 1 — Foundation + LITE

Deliver a working CLI, state/artifact protocol, schemas, fake provider, Claude/Codex discovery, Planner/Producer/Evaluator orchestration, findings loop, evidence validation, final gate, status/resume/report, Git checkpoints, and LITE fixtures.

LITE must be solid before PRO is introduced.

### Milestone 2 — Provider/model adaptation

Complete local setup wizard, provider probes, model capability router, policies, subscription-only protections, and cross-provider assignment rules.

### Milestone 3 — Guardian

Implement OPEN/GUARDED/LOCKED policy engine, command classification, protected paths, scope enforcement hooks, secret redaction, and production gates.

### Milestone 4 — PRO

Add Architect, Tester, Fixer, progress detector, automatic LITE→PRO escalation, optional worktree isolation, and PRO fixtures.

### Milestone 5 — FACTORY

Add task DAG, worker scheduler, isolated worktrees, integrator, system evaluator, PRO→FACTORY escalation, and FACTORY fixtures.

### Milestone 6 — Domain packs

Add `content`, `research`, and `operations` adapters while preserving the same artifact/evidence/final-gate protocol.

### Milestone 7 — Hermes adapter and hardening

Expose stable machine-readable CLI output and integration contract for Hermes and other systems; run full regression, recovery, policy, and benchmark suites.

## 24. Non-goals for initial implementation

The first implementation will not:

- require cloud-hosted orchestration;
- require API keys;
- silently spend API credits;
- provide a web dashboard;
- use GitHub Actions;
- allow agents to mark their own runs complete;
- require both Claude and Codex;
- parallelize LITE;
- use a database server when filesystem state is sufficient;
- embed provider OAuth tokens in project state.

These exclusions protect the simplicity and reliability of the initial runtime.

## 25. Success criteria

The project is ready for a stable release when all of the following are demonstrated locally:

1. a clean clone can complete setup without API keys;
2. Claude-only, Codex-only, and dual-provider configurations are representable and testable through provider probes/fakes;
3. LITE completes a fixture using independent planning/build/evaluation and refuses false completion;
4. interrupted runs resume from persistent state;
5. failed rubric items produce stable findings and are re-verified after fixes;
6. Final Gate rejects incomplete or unverified work;
7. Guardian modes enforce their documented boundaries;
8. PRO executes Builder/Tester/Evaluator as distinct roles and escalates when configured rules are triggered;
9. FACTORY executes a dependency-aware task graph and validates integration before completion;
10. the automated test suite passes without requiring a live paid provider;
11. no GitHub Actions workflows exist;
12. documentation allows a new machine to clone, set up, diagnose, and run the harness successfully.

## 26. Architectural invariants

These are non-negotiable unless the design specification itself is explicitly revised:

- Producer != approver.
- `UNVERIFIED` never equals `PASS`.
- Final completion is deterministic.
- LITE stays simple.
- Files/artifacts are the coordination protocol.
- Runs are resumable without conversational memory.
- Subscription-first is the default.
- Missing providers cause adaptation, not hard failure when another valid provider exists.
- API spending is never silently enabled.
- Complexity and risk are separate.
- Guardian enforcement scales with risk.
- Parallel workers never share a writable checkout.
- FACTORY may compose LITE and PRO internally.
- The harness remains domain-extensible without duplicating its core loop.
- GitHub Actions are not used.
