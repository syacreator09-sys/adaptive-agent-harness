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
4. Read the returned `run_id`, `run_dir`, `profile`, and `guardian`.
5. All agents receive the exact `run_dir`. AAH coordination files live there; product code remains in the project.

## Universal rules

- Fresh subagent execution every handoff; never reuse evaluator context.
- Producer cannot approve its own work.
- Planner/evaluator/reviewers do not modify product code.
- Do not read or copy `.env` values; `.aah/project.json` contains variable names only.
- Wait for explicit completion from each subagent before dispatching the next.
- Sequential by default. FACTORY may parallelize only independent tasks in isolated worktrees; otherwise use safe sequential order.
- After every evaluation run `.aah/bin/factory gate <run_id>`. `UNVERIFIED` is failure to prove, not PASS.
- If the gate fails, use the reported findings; never accept a verbal “looks good”.

## LITE

Preserve the minimal reliable loop:

1. `aah-planner` writes `SPEC.md` and `RUBRIC.json` inside `run_dir`.
2. `aah-builder` builds the full SPEC. It never edits SPEC/RUBRIC/FINDINGS.
3. Fresh `aah-evaluator` executes every rubric criterion and writes `RUBRIC.json`, `FINDINGS.json`, and `EVIDENCE.jsonl` inside `run_dir`.
4. Run Final Gate. If PASS, stop.
5. If FAIL and fewer than 3 evaluation passes, dispatch `aah-builder` in fix-only mode using open findings, then dispatch a fresh evaluator.
6. After 3 failed passes, stop LITE and recommend/perform escalation to PRO rather than looping indefinitely.

## PRO

1. `aah-planner` → SPEC/RUBRIC.
2. `aah-architect` → `ARCHITECTURE.md`.
3. `aah-builder` → implementation.
4. `aah-tester` → technical execution evidence.
5. Fresh `aah-evaluator` → rubric/findings/evidence.
6. Final Gate.
7. On failure, `aah-fixer` repairs only open findings, then tester + fresh evaluator run again. Maximum 5 passes.
8. If progress stalls for two passes or the work becomes multi-workstream/cross-service, escalate to FACTORY.

## FACTORY

1. Planner produces SPEC/RUBRIC.
2. Architect produces `ARCHITECTURE.md` and `TASKS.json` with a DAG and per-task acceptance criteria/profile hints.
3. Dispatch `aah-worker` for each dependency-ready task. Keep workers isolated when running concurrently; otherwise run sequentially.
4. After every worker, dispatch a **fresh `aah-task-evaluator`** against that task acceptance contract. A failed/unverified task returns to a fresh worker fix pass; never integrate an unverified task.
5. `aah-integrator` integrates only independently PASSed task outputs.
6. `aah-system-tester` verifies the integrated system.
7. Fresh `aah-evaluator` verifies the global rubric.
8. `aah-security-reviewer` performs security/secret/dependency review.
9. `aah-final-reviewer` challenges scope and completeness but cannot set DONE.
10. Run deterministic Final Gate. Only the gate can finish the run.

When the user explicitly requests `lite`, `pro`, or `factory`, honor it instead of auto selection. For content/research/operations, prefer the external `factory` CLI because it performs domain/tool routing; native Claude mode is optimized for code-domain orchestration.
