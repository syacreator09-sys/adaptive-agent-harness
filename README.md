# Adaptive Agent Harness (AAH)

**Adaptive Agent Harness** is a local, subscription-first multi-agent runtime for work that must be **specified, built, independently verified, repaired, re-verified, and accepted only with evidence**.

AAH has three adaptive orchestration levels:

- **LITE** — deliberately minimal: Planner → Builder → fresh Evaluator.
- **PRO** — adds Architect, independent technical Tester and dedicated Fixer.
- **FACTORY** — decomposes large systems into a validated DAG of sealed LITE/PRO task mini-harnesses, then integrates and verifies the complete system.

The number of agents changes by level; the doctrine does not:

> A producer never approves its own work. Agents are fresh independent invocations. They coordinate through persistent artifacts and executable evidence. Only deterministic gates can set DONE.

AAH installs **no GitHub Actions**. Its default billing policy is `subscription_only`; it does not silently fall back to paid API-key usage.

---

## 1. Install into a new or existing project

```bash
git clone https://github.com/syacreator09-sys/adaptive-agent-harness.git
cd adaptive-agent-harness
bash install.sh /path/to/your-project
```

`install.sh`:

1. requires Python 3.11+ but downloads no Python dependencies;
2. works with a new directory or an existing repository;
3. copies a self-contained runtime to `<project>/.aah/runtime`;
4. creates `.aah/bin/factory`, `.aah/bin/aah`, Guardian and tool-adapter wrappers;
5. initializes Git only when the target has no repository, unless `AAH_NO_GIT_INIT=1`;
6. detects stacks, commands, instruction files, providers, local tools and MCP metadata;
7. records `.env*` variable **names/classifications only**, never their values;
8. installs AAH-prefixed Claude Code agents plus the `/aah` skill without replacing unrelated project agents/skills;
9. merges one idempotent `PreToolUse` Guardian hook into Claude settings when the existing JSON is valid;
10. preserves malformed user configuration instead of guessing a repair;
11. adds an idempotent AAH block to `AGENTS.md` while preserving existing content;
12. installs named Codex permission profiles only when Codex is detected and never changes the user's default profile;
13. adds `.aah/` to `.gitignore`;
14. never creates `.github/workflows/*`.

Check the installation:

```bash
.aah/bin/factory doctor --json
```

`doctor` returns non-zero when no configured provider session is ready or when a project MCP configuration is invalid. An installed CLI and an authenticated subscription session are reported separately.

---

## 2. Core invariants

Every profile follows these rules:

1. **fresh brain per dispatch/pass** — no evaluator context reuse;
2. **no direct agent-to-agent messaging** — coordination is through files/Git/orchestrator state;
3. **Producer != Evaluator**;
4. **Planner defines requirements once**; runtime seals them before implementation;
5. **Builder/Fixer cannot rewrite acceptance criteria or findings**;
6. **Evaluator/Tester/Reviewers cannot modify product code**;
7. **UNKNOWN / UNVERIFIED != PASS**;
8. **PASS requires explicit positive evidence**;
9. **critical/major open findings block DONE**;
10. **agent failure retries once with a fresh invocation, then fails the phase**;
11. **fixes are bounded to explicit findings; no opportunistic refactoring**;
12. **Git checkpoints prevent duplicate crossed-message fixes from being applied again within the current run**;
13. **Final Gate is deterministic code, not model prose**;
14. **secrets and protected coordination artifacts are runtime-owned**.

---

## 3. Sealed acceptance contract

The Planner initially creates:

```text
SPEC.md
RUBRIC.json
```

AAH then normalizes and seals them into:

```text
SPEC.md
RUBRIC_BASELINE.json
RUBRIC_STATUS.json
CONTRACT.json
```

`CONTRACT.json` contains SHA-256 integrity hashes for the normalized SPEC and baseline rubric. After sealing:

- Builder cannot change SPEC/baseline;
- Evaluator cannot remove or weaken criteria;
- Final Gate rejects hash mismatches;
- evaluation changes only `RUBRIC_STATUS.json` plus findings/evidence.

A typical criterion is binary:

```json
{
  "id": "R-003",
  "required": true,
  "criterion": "POST /login with an invalid password returns 401"
}
```

A PASS status must reference evidence:

```json
{
  "id": "R-003",
  "status": "PASS",
  "evidence": ["E-R-003-P2"]
}
```

and that evidence must independently contain `"ok": true`.

---

## 4. LITE — minimal base architecture

LITE intentionally stays small:

```text
Orchestrator
    │
    ▼
Planner — fresh brain
    │
    ├─ SPEC.md
    └─ RUBRIC.json
    │
    ▼
Runtime seals contract + Git planning checkpoint
    │
    ▼
Builder — fresh brain
    │
    ├─ product changes
    └─ BUILD_REPORT.md
    │
    ▼
Evaluator — fresh brain
    │
    ├─ RUBRIC_STATUS.json
    ├─ FINDINGS.md / FINDINGS.json
    ├─ EVALUATION_REPORT.md
    └─ evidence
    │
    ├─ PASS ─────────────► Final Gate
    │
    └─ FAIL
        │
        ▼
Builder — NEW brain, FIX mode only
        │
        ▼
Evaluator — NEW brain
```

Normal maximum: **3 evaluation passes**.

If a gate fails but the evaluator produced no actionable finding, LITE re-verifies with a fresh Evaluator instead of letting Builder guess. Repeated blocking findings or exhaustion of the bounded loop signal escalation to PRO.

LITE does **not** add Architect, Tester, Integrator, security reviewer or a DAG for simple work.

---

## 5. PRO — same doctrine, stronger separation

```text
Planner
  ↓ sealed contract
Architect
  ↓ ARCHITECTURE.md
Builder
  ↓
Tester — fresh technical verifier
  ↓
Evaluator — fresh acceptance verifier
  ├─ PASS → Final Gate
  └─ FAIL
       ↓
     Fixer — fresh, findings only
       ↓
     Tester — NEW
       ↓
     Evaluator — NEW
```

The roles answer different questions:

- **Architect:** how should this be structured technically?
- **Builder:** implement the sealed contract.
- **Tester:** does it execute/build/test correctly?
- **Evaluator:** does it actually satisfy every sealed acceptance criterion?
- **Fixer:** repair only explicit open findings.

PRO requires domain-specific technical evidence, not merely any positive evidence record. Default maximum: **5 evaluation passes**. A stalled run gets one fresh Architect re-diagnosis; persistent systemic/multi-workstream failure signals FACTORY.

---

## 6. FACTORY — hierarchical multi-orchestration

FACTORY is for work that genuinely needs independent workstreams:

```text
Global Planner
      ↓
sealed global SPEC/RUBRIC
      ↓
Architect
      ↓
validated TASKS.json DAG
      ↓
┌──────────────┬──────────────┬──────────────┐
│ Task T1      │ Task T2      │ Task T3      │
│ LITE mini    │ PRO mini     │ LITE mini    │
│ harness      │ harness      │ harness      │
│              │              │              │
│ Worker       │ Worker       │ Worker       │
│ Evaluator    │ Tester       │ Evaluator    │
│ Task Gate    │ Evaluator    │ Task Gate    │
│              │ Task Gate    │              │
└──────────────┴──────────────┴──────────────┘
      ↓ only independently accepted tasks
Integrator
      ↓
System Tester
      ↓
Global Evaluator
      ↓
Security Reviewer (code/operations)
      ↓
Final Reviewer
      ↓
Final Gate
```

Every task has its own sealed mini-contract:

```text
tasks/T-001/
├── TASK_SPEC.md
├── SPEC.md
├── RUBRIC.json
├── RUBRIC_BASELINE.json
├── RUBRIC_STATUS.json
├── CONTRACT.json
├── FINDINGS.md
├── FINDINGS.json
├── EVIDENCE.jsonl
└── reports/
```

`TASKS.json` is rejected unless it has at least one task and every task has:

- a path-safe unique `id`;
- `profile`: `lite` or `pro`;
- `depends_on`: valid task IDs;
- non-empty measurable `acceptance` criteria;
- optional bounded `scope`.

Cycles, missing dependencies, invalid IDs, empty acceptance criteria and nested FACTORY tasks fail validation. FACTORY never silently fabricates a generic DAG.

Safe scheduling is sequential by default. Parallel work is appropriate only when the host supplies real worktree/sandbox isolation and the tasks do not share mutable state/files.

---

## 7. Escalation without shared reasoning

Automatic profile escalation creates a **new child run**:

```text
LITE parent
   ↓ artifact-only handoff
PRO child, fresh brains
   ↓ if required
FACTORY child, fresh brains
```

The child receives:

- `SPEC.md`;
- the same acceptance baseline as its initial rubric;
- persistent open findings;
- `PARENT_RUN.json` / `ESCALATION_CONTEXT.json`.

It does **not** inherit the parent's `RUBRIC_STATUS.json` or `EVIDENCE.jsonl` as proof. The child seals its own contract and must re-verify independently.

---

## 8. Evidence

External AAH runners ingest returned evidence through the runtime. Native `/aah` uses a draft/append protocol:

```text
Verifier
  ↓
EVIDENCE_DRAFT.json
  ↓
factory evidence-ingest
  ↓ redaction + append-only write
EVIDENCE.jsonl
```

Examples:

```bash
.aah/bin/factory evidence-ingest RUN-... \
  --file .aah/runs/RUN-.../EVIDENCE_DRAFT.json

.aah/bin/factory evidence-ingest RUN-... \
  --file .aah/runs/RUN-.../tasks/T-001/EVIDENCE_DRAFT.json
```

Agents cannot replace `EVIDENCE.jsonl` directly. Corrupt evidence rows cause Final Gate to fail closed.

---

## 9. Guardian and filesystem ownership

Guardian is independent from orchestration complexity:

```text
OPEN
GUARDED
LOCKED
```

Examples:

```bash
.aah/bin/factory run "fix this component" --profile lite --guardian guarded
.aah/bin/factory run "change production auth" --profile pro --guardian locked
```

Claude Code receives a `PreToolUse` enforcement hook for:

```text
Bash | Read | Write | Edit | NotebookEdit | Grep | Glob
```

The hook blocks sensitive/out-of-project paths and enforces role ownership of coordination artifacts. Review brains are restricted to bounded verification commands. Runtime-owned files such as `CONTRACT.json`, `RUBRIC_BASELINE.json`, `STATE.json`, `EVENTS.jsonl` and `EVIDENCE.jsonl` cannot be rewritten by agents.

Codex execution uses `read-only` or `workspace-write` sandbox plus AAH named permission profiles when supported. AAH never switches Codex to unrestricted full-access automatically.

---

## 10. Project Adapter and environment isolation

`factory setup` writes safe metadata to:

```text
.aah/project.json
.aah/capabilities.json
.aah/factory.local.yaml
```

It detects:

- stack/manifests/package scripts;
- probable test/build commands;
- project instruction files;
- Git state/worktree state;
- `.env*` filenames and variable names/classes only;
- Claude/Codex availability/auth metadata;
- local tools;
- safe MCP server metadata.

All ambient secret-looking environment variables are removed from agent subprocesses by default. Reviewers never receive project secrets. A producer can receive a secret only when:

1. Project Adapter discovered the variable name;
2. the task explicitly declares that name in `required_env`;
3. the role is allowed to produce/modify work;
4. it is not an API credential stripped by subscription-only policy.

---

## 11. Adaptive tools

Agents declare capabilities; Tool Router resolves them against the current machine/provider.

Examples:

- Git → local `git`;
- browser → Playwright when available;
- containers → Docker;
- media validation → FFmpeg/ffprobe;
- security → Semgrep;
- Claude web → `WebSearch` / `WebFetch`;
- image/video/voice/custom web → optional local AAH adapters.

Configure local adapters with executable/wrapper commands:

```bash
export AAH_TOOL_IMAGE="/path/to/my-image-wrapper"
export AAH_TOOL_VIDEO="/path/to/my-video-wrapper"
```

Agents see only:

```text
.aah/bin/tool-adapter image
.aah/bin/tool-adapter video
```

AAH does not persist the adapter command value. Prefer wrappers whose authentication is managed by the underlying tool/configuration rather than embedding tokens in the adapter command itself.

Missing optional capabilities may be omitted. A task that explicitly lists a missing `required_tools` capability stops instead of pretending verification occurred.

---

## 12. MCP routing

AAH discovers MCP metadata without storing MCP credential values.

### Claude external runtime

For a task that requests no MCP, AAH uses strict MCP mode so project/user MCP servers are not implicitly loaded into that subprocess. When a task declares:

```json
{
  "required_mcp": ["github"]
}
```

AAH verifies the server exists in project `.mcp.json`, loads that config in strict mode and exposes the selected server tool pattern to the Claude invocation. Missing required MCP stops the dispatch.

### Codex

AAH safely discovers configured MCP server names from project/user Codex configuration and validates required names. Codex owns its MCP lifecycle through its configuration; AAH does **not** claim per-run technical disabling of unselected Codex MCP servers where the CLI does not expose a verified control for it. The agent context is still instructed to use only selected servers.

AAH never installs an arbitrary MCP server merely because an agent requested one.

---

## 13. Providers and model routing

Default billing:

```yaml
billing:
  mode: subscription_only
  api_fallback: false
```

Provider child environments remove `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` and `OPENAI_API_KEY` in subscription-only mode. Authentication remains owned by the installed Claude Code/Codex CLI session.

AAH routes stable **capabilities**, then resolves a model preference for the provider:

```text
deep_reasoning
strong_coding
architecture_high
fast_verification
independent_review
security_review
integration_high
```

Current defaults are adaptive rather than permanent pins:

- Claude high-reasoning/coding → Opus-class (`opus`, with current exact candidates/fallbacks);
- Claude independent/fast verification → Sonnet-class (`sonnet`, with current candidates/fallbacks);
- Codex high capability → GPT-5.6 Sol class;
- Codex balanced verification → Terra/Luna class depending policy.

External runners fall back to the next configured candidate **only when the CLI explicitly reports model-selection/access unavailability**. Arbitrary runtime/tool errors are not replayed on another model. The final fallback is the user's CLI default.

Native Claude agent files use `model: inherit` for compatibility while recording the recommended capability/class in each agent definition.

---

## 14. Native Claude Code mode

After installation, open Claude Code in the target project and use:

```text
/aah "build the requested feature"
```

The native bridge dispatches AAH-prefixed subagents and uses the same persistent contracts/gates. Important helper commands include:

```text
factory init-run
factory seal-rubric
factory evidence-ingest
factory prepare-tasks
factory task-gate
factory gate
factory escalate
```

Native mode is optimized for code-domain orchestration. For content/research/operations, prefer external runtime mode so domain Tool/MCP/Env routing is enforced directly by AAH.

---

## 15. External CLI

```bash
.aah/bin/factory run "fix this endpoint" --profile lite
.aah/bin/factory run "build the complete API" --profile pro
.aah/bin/factory run "build the full multi-service platform" --profile factory
.aah/bin/factory run "choose for me" --profile auto
```

Additional commands:

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
factory gate
factory escalate
factory evidence-ingest   # installed wrapper helper
factory prepare-tasks     # installed wrapper helper
factory task-gate         # installed wrapper helper
```

`rollback` is dry-run by default and refuses to destroy a baseline that was already dirty unless the user explicitly overrides that protection.

---

## 16. Run artifacts

```text
.aah/runs/RUN-YYYYMMDD-NNN/
├── REQUEST.json
├── SPEC.md
├── RUBRIC.json
├── RUBRIC_BASELINE.json
├── RUBRIC_STATUS.json
├── CONTRACT.json
├── STATE.json
├── EVENTS.jsonl
├── AGENTS.jsonl
├── FINDINGS.md
├── FINDINGS.json
├── EVIDENCE.jsonl
├── ARCHITECTURE.md           # PRO / FACTORY
├── TASKS.json                # FACTORY
├── TASK_OUTPUTS.json         # FACTORY runtime-owned
├── PARENT_RUN.json           # escalated child
├── ESCALATION_CONTEXT.json   # escalated child
├── checkpoints/
├── reports/
├── logs/
├── screenshots/
├── artifacts/
├── tasks/                    # FACTORY sealed task harnesses
├── FINAL_REPORT.json
└── FINAL_REPORT.md
```

`AGENTS.jsonl` records auditable role/session/provider/model/capability/MCP metadata so independent invocations can be demonstrated after the run without exposing private reasoning.

---

## 17. Local release gate

AAH deliberately has no GitHub Actions. Before promoting a release, run locally:

```bash
bash scripts/release-check.sh
```

It verifies:

- `install.sh` shell syntax;
- Python compilation;
- canonical agent definitions have no drift;
- complete unittest suite;
- absence of GitHub Actions;
- fresh install into a synthetic existing project;
- preservation of existing `AGENTS.md`/hooks;
- safe `.env` and MCP metadata with no test secret values persisted;
- native helper CLIs;
- installer idempotence.

Do not claim a release is ready until this command exits `0` and prints:

```text
AAH RELEASE CHECK: PASS
```

---

## 18. Maintenance

Regenerate versioned Claude agent definitions from the canonical registry:

```bash
bash scripts/sync-agents.sh
```

Then run the release gate again.

## License

MIT.
