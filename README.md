# Adaptive Agent Harness (AAH)

**Adaptive Agent Harness** is a subscription-first multi-agent runtime for work that must be **built, independently verified, repaired, re-verified, and accepted only with evidence**.

It supports three power levels from one repository:

- **LITE** — minimal Planner → Builder → Evaluator loop with fresh independent agents, file-based coordination, binary acceptance criteria, Git checkpoints, findings, and bounded repair loops.
- **PRO** — adds architecture, technical testing, dedicated fixing, progress detection, and stronger isolation.
- **FACTORY** — decomposes large systems into a task DAG, runs bounded workers, integrates them, system-tests the result, performs independent/security review, and passes a deterministic Final Gate.

No GitHub Actions are installed. No API key is required. Claude Code and/or Codex CLI can use their existing authenticated subscriptions.

## Why

The producer is never allowed to approve its own work. Every required criterion is one of:

- `PASS` — verified with admissible evidence;
- `FAIL` — proven failure;
- `UNVERIFIED` — not proven, therefore **not PASS**.

The deterministic Final Gate, not an agent sentence, decides completion.

## Install into any project

Clone AAH once, then install it into a new or existing project:

```bash
git clone https://github.com/syacreator09-sys/adaptive-agent-harness.git
cd adaptive-agent-harness
./install.sh ~/path/to/your-project
```

The installer:

1. requires Python 3.11+ but no Python packages from the network;
2. copies a self-contained AAH runtime into `<project>/.aah/runtime`;
3. creates `<project>/.aah/bin/factory`;
4. initializes Git if the project has none (disable with `AAH_NO_GIT_INIT=1`);
5. inspects the existing project before modifying it;
6. stores only `.env` **variable names/classifications**, never values;
7. detects stack, test/build commands, Claude/Codex, Git, Docker, Playwright, FFmpeg, Semgrep and other local tools;
8. installs uniquely named Claude Code bridge agents/skill without replacing unrelated `.claude` files;
9. appends an idempotent AAH block to `AGENTS.md` rather than replacing existing instructions;
10. adds `.aah/` to `.gitignore`;
11. never creates `.github/workflows/*`.

## First check

```bash
.aah/bin/factory doctor --json
```

Provider modes adapt automatically:

- Claude only → all roles use fresh Claude sessions;
- Codex only → all roles use fresh Codex executions;
- both → build/review is cross-provider when possible.

With subscription-only mode, `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are removed from provider child-process environments. AAH never silently falls back to paid API usage.

## Run

```bash
.aah/bin/factory run "add a reservations dashboard" --profile auto
```

Force a level when useful:

```bash
.aah/bin/factory run "fix this endpoint" --profile lite
.aah/bin/factory run "build the complete API" --profile pro
.aah/bin/factory run "build the full multi-service platform" --profile factory
```

Guardian is independent from complexity:

```bash
.aah/bin/factory run "change production auth" --profile lite --guardian locked
```

Modes:

- `open` — routine local work, universal destructive commands still blocked;
- `guarded` — default protection for project work;
- `locked` — production/auth/payments/infra-sensitive work with stricter gates.

For Claude Code, `install.sh` also installs an idempotent `PreToolUse` Guardian hook that enforces dangerous-command and sensitive-path rules before tools execute. Existing Claude hooks are preserved. Codex executions use its native `read-only`/`workspace-write` sandbox and are never switched to full-access automatically.

## Claude Code native mode

After installation, open Claude Code inside the target project and run:

```text
/aah "build the requested feature"
```

The native bridge uses fresh Claude subagents instead of launching a nested Claude CLI. It still uses AAH run artifacts and the deterministic `factory gate` command.

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
factory init-run   # native-agent bridge support
factory gate       # deterministic completion check
```

## Project Adapter and environment routing

AAH is designed for both blank repositories and mature projects. `factory setup` creates `.aah/project.json` with:

- detected stacks/manifests;
- existing instruction files (`CLAUDE.md`, `AGENTS.md`, etc.);
- Git branch/base/dirty state;
- package scripts and probable build/test commands;
- `.env*` filenames and variable **names only**;
- classification of names as `config` or `secret`;
- local tool capability map.

Project env values are not copied into AAH state. Review agents do not receive project secret environment values. Implementation agents receive secret-valued environment variables only when a task explicitly declares them; provider authentication remains CLI-managed.

## Adaptive Tool Router

Tools are not hardcoded globally. Each agent declares capabilities, each task may add requirements, and Tool Router resolves them against the current machine. For example:

- browser → Playwright when available;
- container work → Docker when available;
- media validation → FFmpeg when available;
- security → Semgrep when available;
- Node/Python/Go/Rust tools follow the detected project stack.

Missing optional tools degrade the plan; missing tools explicitly marked `required_tools` stop the task instead of pretending verification occurred.

## Profiles

### LITE

```text
Planner → Builder → Evaluator
                    │
              findings?
                    │
              Builder FIX
                    │
             fresh Evaluator
                    │
               Final Gate
```

Default maximum: 3 evaluation passes. If LITE cannot make progress it signals escalation to PRO.

### PRO

```text
Planner → Architect → Builder → Tester → Evaluator
                                      │
                                   Findings
                                      │
                                    Fixer
                                      │
                              Tester → Evaluator
                                      │
                                  Final Gate
```

Default maximum: 5 passes. Repeated no-progress triggers architectural re-diagnosis and can escalate to FACTORY.

### FACTORY

```text
Router → Planner → Architect → Task DAG → Workers
                                        ↓
                                    Integrator
                                        ↓
                                  System Tester
                                        ↓
                                    Evaluator
                                        ↓
                                 Security Review
                                        ↓
                                   Final Review
                                        ↓
                                    Final Gate
```

Tasks include dependency edges and may carry LITE/PRO profile hints. The safe scheduler is sequential by default; isolated parallelism can be added where the host provides reliable worktree/sandbox control.

## Domain packs

The same protocol can be used beyond code:

```bash
factory run "create six verified carousel assets" --domain content
factory run "research this market with verified claims" --domain research
factory run "build and dry-run this automation" --domain operations
```

Domain role routing changes the producer/evaluator identities and evidence types while preserving independent verification and Final Gate.

## Run artifacts

Every execution is resumable from disk:

```text
.aah/runs/RUN-YYYYMMDD-NNN/
├── REQUEST.json
├── SPEC.md
├── RUBRIC.json
├── ARCHITECTURE.md       # PRO/FACTORY
├── TASKS.json            # FACTORY
├── STATE.json
├── FINDINGS.json
├── EVIDENCE.jsonl
├── FINAL_REPORT.md
├── logs/
├── screenshots/
└── artifacts/
```

Agents coordinate through artifacts, not hidden shared conversational memory.

## Models

Roles request capabilities rather than permanent model versions. Defaults use stable provider aliases:

- Claude planning/architecture under `quality` → `opus` alias;
- routine Claude execution/review → `sonnet` alias;
- Codex → the user's current CLI/subscription default unless locally overridden.

Machine-specific overrides live in ignored `.aah/factory.local.yaml`, so the same repository can clone onto different machines without editing source.

## Test AAH itself

AAH's automated suite uses deterministic scripted providers; it does not consume a Claude/Codex subscription:

```bash
python -m unittest discover -s tests -v
bash -n install.sh
```

Real-provider testing is intentionally local/opt-in. There are **no GitHub Actions**.

## License

MIT.
