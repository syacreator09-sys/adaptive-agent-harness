# AAH 0.2 release candidate test protocol

This branch is not promoted to `main` until the local release gate is green. There are no GitHub Actions.

## 1. Clone the exact release-candidate branch

```bash
git clone -b hardening/lite-pro-factory-v2 https://github.com/syacreator09-sys/adaptive-agent-harness.git
cd adaptive-agent-harness
```

Confirm:

```bash
git branch --show-current
# hardening/lite-pro-factory-v2
```

## 2. Deterministic release gate — no model subscription consumed

```bash
bash scripts/release-check.sh
```

Required final line:

```text
AAH RELEASE CHECK: PASS
```

This covers Python/shell syntax, full unittest suite, sealed contracts, Final Gate, Guardian, provider command construction, MCP metadata/routing, env/secret isolation, installer idempotence, agent-definition drift and fresh-install smoke checks.

If any check fails, do not work around it manually. Capture the complete failing test/error and repair the root cause on the release-candidate branch, then run the entire release gate again.

## 3. Real provider smoke — consumes the existing CLI subscription/session

First verify authentication:

```bash
claude auth status 2>/dev/null || true
codex login status 2>/dev/null || true
```

Run one provider strategy at a time if desired:

```bash
AAH_SMOKE_PROVIDER=claude bash scripts/provider-smoke.sh lite
AAH_SMOKE_PROVIDER=codex  bash scripts/provider-smoke.sh lite
```

When both CLIs are available, test cross-provider routing:

```bash
AAH_SMOKE_PROVIDER=both bash scripts/provider-smoke.sh lite
AAH_SMOKE_PROVIDER=both bash scripts/provider-smoke.sh pro
AAH_SMOKE_PROVIDER=both bash scripts/provider-smoke.sh factory
```

Required final line for each:

```text
AAH PROVIDER SMOKE: PASS
```

The smoke project is copied to a temporary Git repository, so AAH never modifies this source checkout. Set `AAH_KEEP_SMOKE=1` to preserve the temporary project for inspection.

## 4. Inspect independence evidence

For a kept run:

```bash
cat .aah/runs/RUN-*/AGENTS.jsonl
cat .aah/runs/RUN-*/EVENTS.jsonl
cat .aah/runs/RUN-*/FINAL_REPORT.md
```

Verify:

- Planner, Builder/Worker, Tester and Evaluator session IDs differ;
- later evaluation passes have new session IDs;
- the producer never appears as the gate authority;
- `CONTRACT.json` and `RUBRIC_BASELINE.json` exist;
- required PASS criteria reference stable `E-*` IDs;
- open critical/major findings are zero when DONE is true;
- FACTORY task directories have their own sealed contracts;
- integration starts only after all task gates pass.

## 5. Native Claude Code bridge test

Install AAH into a disposable project:

```bash
bash install.sh /tmp/aah-native-test
cd /tmp/aah-native-test
```

Open Claude Code there and invoke:

```text
/aah "Create a tiny Python function greet(name) that returns Hello, <name>!, add a unittest, and verify it. Use LITE."
```

Inspect `.aah/runs/...` and verify the flow is Planner → sealed contract → Builder → fresh Evaluator → deterministic gate. The Evaluator must not modify product code.

For PRO/FACTORY native tests, use a disposable project only. Run `factory gate`/`factory task-gate` exactly as instructed by the `/aah` skill; do not accept a verbal model claim as completion.

## 6. MCP check

A project `.mcp.json` may be added with a harmless local/mock server. Then run:

```bash
.aah/bin/factory doctor --json
```

Confirm that server names/transport/env/header **names** appear but credential values do not. A required missing MCP must stop the dispatch. Claude external runs use strict MCP selection. Codex MCP remains provider/config managed where the CLI does not expose a verified per-run disable control.

## 7. Promotion rule

Promote to `main` only after:

1. `bash scripts/release-check.sh` prints PASS;
2. at least LITE real-provider smoke passes for the provider configuration to be used;
3. PRO and FACTORY smoke pass before calling those profiles release-ready;
4. no `.github/workflows/*` exists;
5. the release candidate is reconciled with any newer `main` commits without dropping their fixes.
