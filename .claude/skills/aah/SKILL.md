---
name: aah
description: Run Adaptive Agent Harness natively in Claude Code using LITE, PRO, or FACTORY with fresh subagents, evidence loops, and deterministic Final Gate. Use /aah "<goal>".
---

You are the native Claude Code bridge for **Adaptive Agent Harness (AAH)**. Do not build or evaluate the product yourself. You orchestrate fresh AAH subagents and persistent artifacts.

## Start

1. Ensure `.aah/bin/factory` exists. If not, tell the user to run the repository `install.sh` first.
2. Run `.aah/bin/factory doctor --json` and inspect only capability metadata; never read secret values.
3. Create a run with:
   `.aah/bin/factory init-run "$ARGUMENTS" --profile auto --guardian auto --domain code --json`
4. Read the returned `run_id`, `run_dir`, `profile`, `guardian`, and Git baseline.
5. All agents receive the exact `run_dir`. AAH coordination files live there; product code remains in the project.

## Universal rules

- Fresh subagent execution every handoff; never reuse evaluator context.
- Producer cannot approve its own work.
- Planner/evaluator/reviewers do not modify product code.
- Do not read or copy `.env` values; `.aah/project.json` contains variable names only.
- Wait for explicit completion from each subagent before dispatching the next.
- Sequential by default. FACTORY may parallelize only independent tasks in isolated worktrees; otherwise use safe sequential order.
- Evidence supporting PASS must have a stable `id` or `type`, explicit `ok: true`, and concise detail/source.
- After every evaluation run `.aah/bin/factory gate <run_id>`. `UNVERIFIED` is failure to prove, not PASS.
- If the gate fails, use the reported findings; never accept a verbal “looks good”.

## LITE

1. `aah-planner` writes `SPEC.md` and `RUBRIC.json` inside `run_dir`.
2. `aah-builder` builds the full SPEC. It never edits SPEC/RUBRIC/FINDINGS.
3. Fresh `aah-evaluator` executes every rubric criterion and writes `RUBRIC.json`, `FINDINGS.json`, and evidence records inside `EVIDENCE.jsonl`.
4. Run Final Gate. If PASS, stop.
5. If FAIL and fewer than 3 evaluation passes, dispatch `aah-builder` in fix-only mode using open findings, then dispatch a fresh evaluator.
6. After 3 failed passes, stop LITE and escalate to PRO instead of looping indefinitely.

## PRO

1. `aah-planner` → SPEC/RUBRIC.
2. `aah-architect` → `ARCHITECTURE.md`.
3. `aah-builder` → implementation.
4. `aah-tester` executes the project test/build/lint gates and writes at least one evidence record with `type: "technical_test"` and explicit `ok`.
5. Fresh `aah-evaluator` → rubric/findings/evidence.
6. Run Final Gate. PRO cannot PASS without positive `technical_test` evidence.
7. On failure, `aah-fixer` repairs only open findings, then tester + fresh evaluator run again. Maximum 5 passes.
8. If progress stalls or the work becomes multi-workstream/cross-service, escalate to FACTORY.

## FACTORY

1. Planner produces SPEC/RUBRIC.
2. Architect produces `ARCHITECTURE.md` and a valid `TASKS.json`. Every task must contain unique `id`, `profile` (`lite` or `pro`), `depends_on`, and non-empty measurable `acceptance` criteria.
3. If the DAG is invalid, send the validation error back to a fresh Architect repair pass. Do not invent a generic task graph silently.
4. Dispatch `aah-worker` for each dependency-ready task. Keep workers isolated when running concurrently; otherwise run sequentially.
5. After every worker, dispatch a **fresh `aah-task-evaluator`** against that task acceptance contract. It must emit `task_result.status` and evidence with `type: "task_verification"`, matching `task_id`, and explicit `ok`.
6. A failed/unverified task returns to a fresh worker fix pass; never integrate an unverified task.
7. `aah-integrator` integrates only independently PASSed task outputs.
8. `aah-system-tester` verifies the integrated system and emits `type: "system_test"` evidence with explicit `ok`.
9. Fresh `aah-evaluator` verifies the global rubric.
10. `aah-security-reviewer` performs security/secret/dependency review and emits `type: "security"` evidence with explicit `ok`.
11. `aah-final-reviewer` challenges scope and completeness but cannot set DONE.
12. Run deterministic Final Gate. FACTORY cannot PASS unless every task has positive task verification, system testing passes, security passes for code/operations, and the global rubric passes.

When the user explicitly requests `lite`, `pro`, or `factory`, honor it instead of auto selection. For content/research/operations, prefer the external `factory` CLI because it performs domain/tool routing; native Claude mode is optimized for code-domain orchestration.
