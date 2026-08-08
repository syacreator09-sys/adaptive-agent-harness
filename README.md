# Adaptive Agent Harness (AAH)

**Adaptive Agent Harness** is a subscription-first multi-agent runtime for work that must be **planned, built, independently verified, repaired, re-verified, and accepted only with evidence**.

One repository provides three execution levels:

- **LITE** — Planner → Builder → fresh Evaluator, with bounded repair loops.
- **PRO** — adds Architect, independent technical Tester, dedicated Fixer, progress detection, and stronger gates.
- **FACTORY** — decomposes large systems into a validated task DAG, verifies every task independently, integrates only PASSed work, system-tests the result, performs security/final review, and finishes through a deterministic Final Gate.

AAH does **not** require API keys. It adapts to authenticated **Claude Code**, **Codex CLI**, or both. Paid API fallback is disabled by default. There are **no GitHub Actions** in this repository.

## Core rule

The producer never approves its own work.

Every required criterion is one of:

- `PASS` — proven by explicit positive evidence;
- `FAIL` — proven failure;
- `UNVERIFIED` — not proven, therefore not PASS.

Evidence used for PASS must contain a stable `id` or `type` and explicit `ok: true`. Narrative statements such as “looks good” are not sufficient.

The Planner's acceptance rubric is **sealed before implementation**. Evaluators may update result status/evidence, but they cannot remove criteria, weaken `required`, or change the acceptance contract. Final Gate rejects contract drift.

## Install into a new or existing project

```bash
git clone https://github.com/syacreator09-sys/adaptive-agent-harness.git
cd adaptive-agent-harness
./install.sh ~/path/to/your-project
```

If the target directory does not exist, `install.sh` creates it. Existing projects are inspected before AAH modifies its own integration files.

The installer:

1. requires Python 3.11+ and uses only the Python standard library at runtime;
2. copies AAH into `<project>/.aah/runtime`;
3. creates `<project>/.aah/bin/factory`;
4. initializes Git only when the target has no repository, unless `AAH_NO_GIT_INIT=1`;
5. detects stack, package scripts, tests/build commands, Git/worktree state, tools and provider CLIs;
6. records `.env*` variable **names/classifications only**, never their values;
7. installs uniquely named Claude Code AAH agents and `/aah` skill without replacing unrelated agents;
8. merges an idempotent Claude `PreToolUse` Guardian hook while preserving existing valid hooks;
9. adds named Codex AAH filesystem permission profiles only when Codex is present, without changing the user's default profile;
10. appends an idempotent AAH section to `AGENTS.md` instead of replacing existing instructions;
11. adds `.aah/` to `.gitignore`;
12. never creates `.github/workflows/*`.

## First check

```bash
.aah/bin/factory doctor --json
```

AAH distinguishes **installed CLI** from **authenticated subscription session**. Provider modes adapt automatically:

- Claude only → fresh Claude executions/sessions;
- Codex only → fresh Codex executions;
- Claude + Codex → cross-provider build/review when useful.

In subscription-only mode, provider child processes do not inherit `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`, so AAH does not silently switch into API billing.

## Run automatically

```bash
.aah/bin/factory run "add a reservations dashboard" --profile auto
```

Force a profile when useful:

```bash
.aah/bin/factory run "fix this endpoint" --profile lite
.aah/bin/factory run "build the complete API" --profile pro
.aah/bin/factory run "build the full multi-service platform" --profile factory
```

Complexity and risk are independent. A small production auth change can use LITE with a strict Guardian:

```bash
.aah/bin/factory run "change production auth" --profile lite --guardian locked
```

## Native Claude Code mode

After installation, open Claude Code in the target project:

```text
/aah "build the requested feature"
```

Native mode orchestrates fresh AAH subagents and uses the same disk artifacts and deterministic Final Gate. It does not let one subagent inherit another agent's hidden reasoning.

The native flow seals the rubric immediately after Planner output:

```bash
.aah/bin/factory seal-rubric <run_id>
```

When a bounded level is exhausted, native mode creates a **fresh child run** and hands off only persistent artifacts:

```bash
# LITE → PRO
.aah/bin/factory escalate <lite_run_id> --profile pro --json

# PRO → FACTORY
.aah/bin/factory escalate <pro_run_id> --profile factory --json
```

The child receives `PARENT_RUN.json` and `ESCALATION_CONTEXT.json` with normalized parent rubric/findings/report and a new Git baseline. It does not rely on shared conversational memory.

## Profiles

### LITE

```text
Planner
  ↓
sealed SPEC + RUBRIC
  ↓
Builder
  ↓
fresh Evaluator
  ↓
FAIL → Builder FIX → fresh Evaluator
  ↓
Final Gate
```

Default maximum: 3 evaluation passes. When the bounded loop cannot solve the task, auto mode escalates to PRO with artifact handoff.

### PRO

```text
Planner → sealed rubric
   ↓
Architect
   ↓
Builder
   ↓
Technical Tester
   ↓
fresh Evaluator
   ↓
FAIL → Fixer → Tester → fresh Evaluator
   ↓
Final Gate
```

PRO requires domain-specific positive test evidence before it can finish. Repeated no-progress triggers architectural re-diagnosis and can escalate to FACTORY.

### FACTORY

```text
Planner → sealed rubric
   ↓
Architect → validated task DAG
   ↓
Worker(task A) → fresh Task Evaluator
Worker(task B) → fresh Task Evaluator
...
   ↓
Integrator (PASSed tasks only)
   ↓
System/Domain Tester
   ↓
fresh Global Evaluator
   ↓
Security Review (code/operations)
   ↓
Final Reviewer
   ↓
Deterministic Final Gate
```

FACTORY refuses malformed DAGs. Every task requires:

- safe unique `id`;
- `profile: lite|pro`;
- `depends_on` list;
- non-empty measurable `acceptance` criteria.

The Architect receives one repair opportunity with the validation error. If the DAG remains invalid, FACTORY pauses instead of silently inventing a generic task.

Completed FACTORY tasks are persisted in `TASK_OUTPUTS.json`; a resumed run skips only tasks that already passed independent verification.

## Guardian

Guardian is a deterministic enforcement layer, not another developer agent.

- **OPEN** — routine local work; universal destructive actions remain blocked.
- **GUARDED** — default; protects secrets, project boundaries, AAH internals and suspicious/destructive commands.
- **LOCKED** — production/auth/payments/infra-sensitive work with approval gates for production-changing actions.

Claude's `PreToolUse` hook enforces role/path/command rules before tools run. Review agents cannot modify product code. Sensitive reads/writes, project-root escapes, `.env*`, credential directories and protected AAH runtime files are blocked. Grep/Glob are also checked.

Codex executions use AAH's named read-only/workspace permission profiles and native sandboxing; AAH never switches to unrestricted access automatically.

## Project Adapter and environment routing

`factory setup` creates `.aah/project.json` containing:

- detected stacks/manifests;
- existing instruction files (`CLAUDE.md`, `AGENTS.md`, etc.);
- Git branch/base/dirty/worktree state;
- package scripts and probable build/test commands;
- `.env*` filenames and variable names only;
- `config` vs `secret` classification;
- local capability map.

Review/research agents do not receive project secret-valued env vars. Implementation agents receive a project secret only when a task explicitly declares that env name as required.

## Adaptive Tool Router

Tools are resolved **per machine, provider, role and task**. AAH does not claim capabilities that are not actually available.

Examples:

- Claude web-grounded roles can expose `WebSearch` / `WebFetch`;
- Codex filesystem work uses its sandbox, but AAH does not assume Codex web is enabled because that is installation-dependent;
- Git, Docker, Playwright, FFmpeg/FFprobe, Semgrep and language/package tools are discovered locally;
- missing required tools stop the task instead of creating fake verification.

Optional machine-specific adapters can expose external media/search systems:

```bash
export AAH_TOOL_IMAGE=/path/to/image-adapter
export AAH_TOOL_VIDEO=/path/to/video-adapter
export AAH_TOOL_VOICE=/path/to/voice-adapter
export AAH_TOOL_WEB=/path/to/web-search-adapter
```

The same clone can therefore run differently on a Claude-only laptop, a Claude+Codex workstation, or a media-capable production machine without editing AAH core.

## Domain packs

The universal protocol remains:

```text
REQUEST → SPEC → PRODUCE → VERIFY → FINDINGS → FIX → RE-VERIFY → FINAL GATE
```

Available domains:

```bash
factory run "build this feature" --domain code
factory run "create six verified carousel assets" --domain content
factory run "research this market with verified claims" --domain research
factory run "build and dry-run this automation" --domain operations
```

Deterministic domain gates include:

- code / operations → `technical_test`, FACTORY `system_test`;
- content → `content_check`;
- research → `fact_check`;
- every FACTORY task → `task_verification` with matching `task_id`;
- code / operations FACTORY → `security` gate.

Content image/video/voice production requires a real connected adapter when the request needs that medium. Research requires real web capability. AAH stops rather than pretending those tools exist.

## Run artifacts

```text
.aah/runs/RUN-YYYYMMDD-NNN/
├── REQUEST.json
├── SPEC.md
├── RUBRIC.json
├── RUBRIC_BASELINE.json
├── ARCHITECTURE.md       # PRO / FACTORY
├── TASKS.json            # FACTORY
├── TASK_OUTPUTS.json     # FACTORY
├── STATE.json
├── FINDINGS.json
├── EVIDENCE.jsonl
├── PARENT_RUN.json       # escalated child
├── ESCALATION_CONTEXT.json
├── FINAL_REPORT.json
├── FINAL_REPORT.md
├── logs/
├── screenshots/
└── artifacts/
```

Requests, evidence, agent artifacts and report extras pass through secret redaction before persistence. Run/task IDs and artifact paths are validated against traversal escapes.

## Commands

```text
factory setup
factory doctor
factory run
factory status
factory resume
factory eval
factory fix
factory report
factory rollback
factory init-run
factory seal-rubric
factory escalate
factory gate
```

`factory rollback` is dry-run by default. If the project was already dirty at the recorded Git baseline, AAH refuses destructive restore unless the operator explicitly accepts that risk.

## Models

Roles request capabilities rather than permanent model versions. Stable defaults use provider aliases/current CLI defaults:

- Claude planning/architecture under `quality` → `opus` alias;
- routine Claude execution/review → `sonnet` alias;
- Codex → the authenticated CLI/subscription default unless locally overridden.

Machine-specific overrides live in ignored `.aah/factory.local.yaml`.

## Verify AAH itself

AAH's automated suite uses deterministic scripted providers and does not consume Claude/Codex subscriptions:

```bash
python3 -m unittest discover -s tests -v
bash -n install.sh
python3 -m compileall -q factory tests
```

A release smoke test can install into a temporary project and verify the generated CLI/Claude bridge. Real-provider smoke tests are intentionally local and opt-in.

There are **no GitHub Actions**.

## License

MIT.
