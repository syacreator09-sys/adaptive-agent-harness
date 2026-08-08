from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from .config import AAHConfig
from .project_adapter import ProjectAdapter
from .providers import ProviderRegistry
from .tools import ToolRegistry
from .router import AdaptiveRouter
from .agents import AgentRegistry
from .executor import AgentExecutor
from .artifacts import ArtifactStore
from .profiles import LiteRunner, ProRunner, FactoryRunner
from .orchestrator import AutoOrchestrator, create_escalation_child, PROFILE_ORDER
from .domains import role_for, gate_types
from .final_gate import FinalGate, normalize_findings
from .evidence import EvidenceStore
from .codex_profiles import install_profiles
from .contracts import seal_contract
from .gitops import GitCheckpoints
from .events import EventJournal
from .state import RunStateStore
from .models import Phase
from .taskgraph import TaskGraph, TaskGraphError


def _target(args) -> Path:
    return Path(getattr(args, "target", None) or os.getcwd()).resolve()


def _ask_choice(label, choices, default):
    if not sys.stdin.isatty():
        return default
    raw = input(f"{label} [{'/'.join(choices)}] (default {default}): ").strip().lower()
    return raw if raw in choices else default


def _configured_providers(cfg, discovered):
    strategy = cfg.data.get("providers", {}).get("strategy", "auto")
    if strategy == "claude":
        return {
            "claude": discovered.get("claude", {"available": False}),
            "codex": {"available": False, "authenticated": False, "reason": "disabled_by_config"},
        }
    if strategy == "codex":
        return {
            "claude": {"available": False, "authenticated": False, "reason": "disabled_by_config"},
            "codex": discovered.get("codex", {"available": False}),
        }
    return discovered


def _require_router(target: Path, cfg: AAHConfig) -> AdaptiveRouter:
    providers = _configured_providers(cfg, ProviderRegistry.discover())
    router = AdaptiveRouter(providers)
    if router.available():
        return router
    installed = [name for name, info in providers.items() if info.get("available")]
    if installed:
        raise RuntimeError(
            "Provider CLI detected but no authenticated subscription session is ready. "
            "Login to Claude Code/Codex, then run factory doctor."
        )
    raise RuntimeError("No provider CLI detected. Install/login to Claude Code or Codex, then run factory doctor.")


def _runner(target, profile, executor):
    return {"lite": LiteRunner, "pro": ProRunner, "factory": FactoryRunner}[profile](target, executor)


def _roles_for(profile: str, domain: str) -> list[str]:
    canonical = {
        "lite": ["planner", "builder", "evaluator"],
        "pro": ["planner", "architect", "builder", "tester", "evaluator", "fixer"],
        "factory": [
            "planner", "architect", "worker", "tester", "task_evaluator", "fixer",
            "integrator", "system_tester", "evaluator", "security_reviewer", "final_reviewer",
        ],
    }[profile]
    roles: list[str] = []
    for role in canonical:
        if role in {"planner", "builder", "tester", "evaluator", "fixer", "worker"}:
            actual = role_for(domain, role)
        elif role == "system_tester" and domain not in {"code", "operations"}:
            actual = role_for(domain, "tester")
        else:
            actual = role
        if actual not in roles:
            roles.append(actual)
    return roles


def _executor(target: Path, profile: str, domain: str, cfg: AAHConfig, router: AdaptiveRouter) -> AgentExecutor:
    roles = _roles_for(profile, domain)
    assignments = router.assign_roles(
        roles,
        cfg.data["models"]["policy"],
        cfg.data["models"].get("overrides"),
    )
    return AgentExecutor(
        target,
        assignments,
        subscription_only=cfg.data["billing"]["mode"] == "subscription_only",
        registry=AgentRegistry(),
    )


def setup(args):
    target = _target(args)
    target.mkdir(parents=True, exist_ok=True)
    aah = target / ".aah"
    aah.mkdir(exist_ok=True)
    manifest = ProjectAdapter(target).inspect()
    providers = ProviderRegistry.discover()
    tools = ToolRegistry.discover()
    capabilities = {
        "providers": providers,
        "tools": tools,
        "mcp": manifest.get("mcp", {}),
        "secrets_persisted": False,
    }
    (aah / "project.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (aah / "capabilities.json").write_text(json.dumps(capabilities, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    codex_info = providers.get("codex", {})
    codex_permissions = (
        install_profiles(target)
        if codex_info.get("available")
        else {"installed": False, "reason": "codex_unavailable"}
    )
    cfg = AAHConfig.load(target)
    if not args.non_interactive:
        available = [
            name for name, info in providers.items()
            if info.get("available") and info.get("authenticated") is not False
        ]
        suggested = "both" if len(available) > 1 else available[0] if available else "auto"
        cfg.data["providers"]["strategy"] = _ask_choice(
            "Provider strategy", ["auto", "claude", "codex", "both"], suggested
        )
        cfg.data["models"]["policy"] = _ask_choice(
            "Model policy", ["quality", "balanced", "economy"], cfg.data["models"]["policy"]
        )
        cfg.data["execution"]["profile"] = _ask_choice(
            "Default profile", ["auto", "lite", "pro", "factory"], cfg.data["execution"]["profile"]
        )
        cfg.data["guardian"]["mode"] = _ask_choice(
            "Guardian", ["auto", "open", "guarded", "locked"], cfg.data["guardian"]["mode"]
        )
    cfg.data["billing"] = {"mode": "subscription_only", "api_fallback": False}
    cfg.save(target)

    gitignore = target / ".gitignore"
    text = gitignore.read_text(encoding="utf-8", errors="ignore") if gitignore.exists() else ""
    if ".aah/" not in text.splitlines():
        gitignore.write_text(
            text + ("\n" if text and not text.endswith("\n") else "") + ".aah/\n",
            encoding="utf-8",
        )

    print(json.dumps({
        "ok": True,
        "target": str(target),
        "stacks": manifest["stacks"],
        "providers": providers,
        "mcp": manifest.get("mcp", {}).get("servers", []),
        "codex_permissions": codex_permissions,
        "config": str(aah / "factory.local.yaml"),
    }, indent=2))
    return 0


def doctor(args):
    target = _target(args)
    cfg = AAHConfig.load(target)
    providers = ProviderRegistry.discover()
    tools = ToolRegistry.discover()
    project = ProjectAdapter(target).inspect()
    ready = any(
        info.get("available") and info.get("authenticated") is not False
        for info in _configured_providers(cfg, providers).values()
    )
    mcp_errors = [
        item for item in project.get("mcp", {}).get("claude", [])
        if isinstance(item, dict) and item.get("config_error")
    ]
    payload = {
        "ok": ready and not mcp_errors,
        "provider_ready": ready,
        "target": str(target),
        "providers": providers,
        "tools": tools,
        "mcp": project.get("mcp", {}),
        "project": project,
        "billing": cfg.data["billing"],
        "warnings": ["invalid .mcp.json"] if mcp_errors else [],
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"AAH doctor: {target}")
        print("Providers: " + ", ".join(
            f"{name}=installed:{'yes' if info.get('available') else 'no'},"
            f"auth:{'yes' if info.get('authenticated') is True else 'no' if info.get('authenticated') is False else 'unknown'}"
            for name, info in providers.items()
        ))
        print("Stacks: " + (", ".join(project["stacks"]) or "unknown"))
        print("MCP: " + (", ".join(item["name"] for item in project.get("mcp", {}).get("servers", [])) or "none"))
        print("Billing: " + cfg.data["billing"]["mode"])
        print("Ready: " + ("yes" if payload["ok"] else "no"))
    return 0 if payload["ok"] else 3


def run_cmd(args):
    target = _target(args)
    cfg = AAHConfig.load(target)
    router = _require_router(target, cfg)

    def executor_factory(profile, domain):
        return _executor(target, profile, domain, cfg, router)

    requested_profile = args.profile
    if requested_profile == "auto" and cfg.data["execution"].get("profile", "auto") != "auto":
        requested_profile = cfg.data["execution"]["profile"]
    requested_guardian = args.guardian
    if requested_guardian == "auto" and cfg.data["guardian"].get("mode", "auto") != "auto":
        requested_guardian = cfg.data["guardian"]["mode"]

    result = AutoOrchestrator(
        target,
        executor_factory,
        router,
        limits=cfg.data.get("execution", {}),
    ).run(
        args.request,
        domain=args.domain,
        profile=requested_profile,
        guardian=requested_guardian,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["done"] else 2


def _resolve_run(target, run_id):
    store = ArtifactStore(target)
    return store.get_run(run_id) if run_id else store.latest_run()


def status(args):
    run = _resolve_run(_target(args), args.run_id)
    if not run:
        print("No runs", file=sys.stderr)
        return 1
    print(json.dumps(ArtifactStore.read_json(run.run_dir, "STATE.json", {}), indent=2))
    return 0


def report(args):
    run = _resolve_run(_target(args), args.run_id)
    if not run:
        print("No runs", file=sys.stderr)
        return 1
    path = run.run_dir / "FINAL_REPORT.md"
    print(
        path.read_text(encoding="utf-8")
        if path.exists()
        else json.dumps(ArtifactStore.read_json(run.run_dir, "FINAL_REPORT.json", {}), indent=2)
    )
    return 0


def _run_existing(target: Path, run, cfg: AAHConfig, router: AdaptiveRouter):
    request_doc = ArtifactStore.read_json(run.run_dir, "REQUEST.json", {}) or {}
    profile = str(request_doc.get("profile") or "lite")
    guardian = str(request_doc.get("guardian") or "guarded")
    domain = str(request_doc.get("domain") or "code")
    executor = _executor(target, profile, domain, cfg, router)
    runner = _runner(target, profile, executor)
    kwargs: dict[str, Any] = {"guardian": guardian, "domain": domain, "run_id": run.run_id}
    if profile == "lite":
        kwargs["max_passes"] = cfg.data["execution"].get("max_lite_passes", 3)
    elif profile == "pro":
        kwargs["max_passes"] = cfg.data["execution"].get("max_pro_passes", 5)
    return runner.run(str(request_doc.get("request") or "resume"), **kwargs)


def resume(args):
    target = _target(args)
    run = _resolve_run(target, args.run_id)
    if not run:
        print("Run not found", file=sys.stderr)
        return 1
    state = ArtifactStore.read_json(run.run_dir, "STATE.json", {}) or {}
    if state.get("status") == "done":
        return report(args)
    cfg = AAHConfig.load(target)
    router = _require_router(target, cfg)
    result = _run_existing(target, run, cfg, router)
    print(json.dumps(result, indent=2))
    return 0 if result["done"] else 2


def _positive_evidence(run_dir: Path, labels: set[str], task_id: str | None = None) -> bool:
    matched = []
    for record in EvidenceStore(run_dir).all():
        label = str(record.get("type") or record.get("kind") or "")
        if label not in labels:
            continue
        if task_id is not None and str(record.get("task_id") or "") != str(task_id):
            continue
        matched.append(record)
    explicit = [record.get("ok") for record in matched if "ok" in record]
    return bool(explicit) and all(value is True for value in explicit)


def _task_findings(task_dir: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads((task_dir / "FINDINGS.json").read_text(encoding="utf-8"))
    except Exception:
        value = []
    return normalize_findings(value)


def _native_mandatory_gates(run) -> list[dict[str, Any]]:
    request_doc = ArtifactStore.read_json(run.run_dir, "REQUEST.json", {}) or {}
    profile = str(request_doc.get("profile") or "lite")
    domain = str(request_doc.get("domain") or "code")
    gates: list[dict[str, Any]] = []
    if profile == "pro":
        gates.append({
            "name": "domain_tests",
            "ok": _positive_evidence(run.run_dir, gate_types(domain, "pro_test")),
        })
    elif profile == "factory":
        raw = ArtifactStore.read_json(run.run_dir, "TASKS.json", None)
        all_tasks_ok = False
        try:
            graph = TaskGraph(raw)
            task_results = []
            for task in graph.tasks:
                task_dir = run.run_dir / "tasks" / task["id"]
                mandatory = []
                if task["profile"] == "pro":
                    mandatory.append({
                        "name": "task_technical_tests",
                        "ok": _positive_evidence(task_dir, gate_types(domain, "pro_test")),
                    })
                task_results.append(FinalGate(task_dir).evaluate(None, _task_findings(task_dir), mandatory)["done"])
            all_tasks_ok = bool(task_results) and all(task_results)
        except (TaskGraphError, OSError, ValueError):
            all_tasks_ok = False
        gates.append({"name": "task_graph", "ok": all_tasks_ok})
        gates.append({
            "name": "system_test",
            "ok": _positive_evidence(run.run_dir, gate_types(domain, "factory_system")),
        })
        if domain in {"code", "operations"}:
            gates.append({"name": "security", "ok": _positive_evidence(run.run_dir, {"security"})})
    return gates


def eval_cmd(args):
    target = _target(args)
    run = _resolve_run(target, args.run_id)
    if not run:
        print("Run not found", file=sys.stderr)
        return 1
    request_doc = ArtifactStore.read_json(run.run_dir, "REQUEST.json", {}) or {}
    profile = str(request_doc.get("profile") or "lite")
    if profile == "factory":
        print("FACTORY manual eval is intentionally disabled; use factory resume so task/system/security gates cannot be skipped.", file=sys.stderr)
        return 2
    domain = str(request_doc.get("domain") or "code")
    guardian = str(request_doc.get("guardian") or "guarded")
    cfg = AAHConfig.load(target)
    router = _require_router(target, cfg)
    runner = _runner(target, profile, _executor(target, profile, domain, cfg, router))
    context = runner._context(run, guardian)
    state_store = RunStateStore(run.run_dir)
    mandatory = []
    if profile == "pro":
        state_store.transition(Phase.TESTING)
        test_result = runner._dispatch(run, role_for(domain, "tester"), {"mode": "manual_test"}, context)
        evidence = [item for item in test_result.get("evidence", []) if isinstance(item, dict)]
        explicit = [item.get("ok") for item in evidence if "ok" in item]
        mandatory.append({"name": "domain_tests", "ok": bool(explicit) and all(value is True for value in explicit)})
    state_store.transition(Phase.EVALUATING)
    runner._dispatch(run, role_for(domain, "evaluator"), {"mode": "evaluate_only"}, context)
    gate = runner._gate(run, mandatory)
    result = runner._write_report(run, gate, {"manual_eval": True})
    print(json.dumps(result, indent=2))
    return 0 if gate["done"] else 2


def fix_cmd(args):
    target = _target(args)
    run = _resolve_run(target, args.run_id)
    if not run:
        print("Run not found", file=sys.stderr)
        return 1
    request_doc = ArtifactStore.read_json(run.run_dir, "REQUEST.json", {}) or {}
    profile = str(request_doc.get("profile") or "lite")
    if profile == "factory":
        print("FACTORY manual fix is intentionally disabled; use factory resume to preserve per-task mini-harnesses.", file=sys.stderr)
        return 2
    domain = str(request_doc.get("domain") or "code")
    guardian = str(request_doc.get("guardian") or "guarded")
    cfg = AAHConfig.load(target)
    router = _require_router(target, cfg)
    runner = _runner(target, profile, _executor(target, profile, domain, cfg, router))
    context = runner._context(run, guardian)
    state_store = RunStateStore(run.run_dir)
    pending = runner._pending_findings(run)
    if pending:
        state_store.transition(Phase.FIXING)
        role = role_for(domain, "builder" if profile == "lite" else "fixer")
        runner._dispatch(run, role, {"mode": "fix_only", "findings": pending}, context)
    mandatory = []
    if profile == "pro":
        state_store.transition(Phase.TESTING)
        test_result = runner._dispatch(run, role_for(domain, "tester"), {"mode": "test_after_manual_fix"}, context)
        evidence = [item for item in test_result.get("evidence", []) if isinstance(item, dict)]
        explicit = [item.get("ok") for item in evidence if "ok" in item]
        mandatory.append({"name": "domain_tests", "ok": bool(explicit) and all(value is True for value in explicit)})
    state_store.transition(Phase.EVALUATING)
    runner._dispatch(run, role_for(domain, "evaluator"), {"mode": "evaluate_after_fix"}, context)
    gate = runner._gate(run, mandatory)
    result = runner._write_report(run, gate, {"manual_fix": True})
    print(json.dumps(result, indent=2))
    return 0 if gate["done"] else 2


def rollback(args):
    target = _target(args)
    run = _resolve_run(target, args.run_id)
    if not run:
        print("Run not found", file=sys.stderr)
        return 1
    state = ArtifactStore.read_json(run.run_dir, "STATE.json", {}) or {}
    request_doc = ArtifactStore.read_json(run.run_dir, "REQUEST.json", {}) or {}
    base = state.get("git_base") or request_doc.get("git_base")
    if not base:
        print("No recorded git checkpoint; rollback refused.", file=sys.stderr)
        return 2
    if state.get("git_base_dirty") and not args.force_dirty_baseline:
        print(
            "Rollback refused: project already had tracked changes at AAH start. "
            "Commit/stash them first, or use --force-dirty-baseline only if you explicitly accept losing tracked baseline edits.",
            file=sys.stderr,
        )
        return 2
    if not args.apply:
        print(f"Dry run: would restore tracked files from {base}. Re-run with --apply.")
        return 0
    cp = subprocess.run(
        ["git", "-C", str(target), "restore", "--source", str(base), "--staged", "--worktree", "."],
        text=True,
        capture_output=True,
    )
    if cp.returncode:
        print(cp.stderr, file=sys.stderr)
        return cp.returncode
    print(f"Restored tracked files from {base}; untracked files were preserved.")
    return 0


def init_run(args):
    target = _target(args)
    route = AdaptiveRouter(ProviderRegistry.discover()).route(args.request)
    profile = args.profile if args.profile != "auto" else route["profile"]
    guardian = args.guardian if args.guardian != "auto" else route["guardian"]
    store = ArtifactStore(target)
    run = store.create_run(args.request, profile, guardian, args.domain)
    snapshot = GitCheckpoints(target).snapshot()
    state = store.read_json(run.run_dir, "STATE.json", {}) or {}
    state.update({
        "git_base": snapshot.get("head"),
        "git_base_dirty": snapshot.get("dirty", False),
        "git_worktree": snapshot.get("is_linked_worktree", False),
    })
    store.write_json(run.run_dir, "STATE.json", state)
    request_doc = store.read_json(run.run_dir, "REQUEST.json", {}) or {}
    request_doc["git_base"] = snapshot.get("head")
    store.write_json(run.run_dir, "REQUEST.json", request_doc)
    EventJournal(run.run_dir).append(
        "RUN_CREATED",
        run_id=run.run_id,
        profile=profile,
        guardian=guardian,
        domain=args.domain,
        git_base=snapshot.get("head"),
        native_bridge=True,
    )
    payload = {
        "run_id": run.run_id,
        "run_dir": str(run.run_dir),
        "profile": profile,
        "guardian": guardian,
        "route": route,
        "git_base": snapshot.get("head"),
    }
    print(json.dumps(payload) if args.json else json.dumps(payload, indent=2))
    return 0


def seal_rubric_cmd(args):
    target = _target(args)
    run = _resolve_run(target, args.run_id)
    if not run:
        print("Run not found", file=sys.stderr)
        return 1
    if not (run.run_dir / "CONTRACT.json").exists():
        if EvidenceStore(run.run_dir).all() or (run.run_dir / "FINDINGS.json").exists():
            print("Refusing late contract seal: evaluation/finding artifacts already exist.", file=sys.stderr)
            return 2
    contract = seal_contract(run.run_dir)
    store = ArtifactStore(target)
    checkpoint_path = run.run_dir / "checkpoints" / "planning.json"
    checkpoint = (
        store.read_json(run.run_dir, "checkpoints/planning.json", {})
        if checkpoint_path.exists()
        else GitCheckpoints(target).planning_checkpoint(run.run_id)
    )
    if not checkpoint_path.exists():
        store.write_json(run.run_dir, "checkpoints/planning.json", checkpoint)
    state_store = RunStateStore(run.run_dir)
    state = state_store.load()
    state["contract"] = contract
    state["planning_checkpoint"] = checkpoint
    state_store.save(state)
    EventJournal(run.run_dir).append(
        "CONTRACT_SEALED",
        spec_sha256=contract.get("spec_sha256"),
        rubric_sha256=contract.get("rubric_sha256"),
        git_checkpoint=checkpoint.get("head"),
        native_bridge=True,
    )
    print(json.dumps({"ok": True, "run_id": run.run_id, "contract": contract, "checkpoint": checkpoint}, indent=2))
    return 0


def gate_cmd(args):
    target = _target(args)
    run = _resolve_run(target, args.run_id)
    if not run:
        print("Run not found", file=sys.stderr)
        return 1
    findings = ArtifactStore.read_json(run.run_dir, "FINDINGS.json", []) or []
    result = FinalGate(run.run_dir).evaluate(None, findings, _native_mandatory_gates(run))
    if result["done"]:
        state_store = RunStateStore(run.run_dir)
        state_store.transition(Phase.DONE, status="done")
    print(json.dumps(result, indent=2))
    return 0 if result["done"] else 2


def escalate_cmd(args):
    target = _target(args)
    parent = _resolve_run(target, args.run_id)
    if not parent:
        print("Run not found", file=sys.stderr)
        return 1
    request_doc = ArtifactStore.read_json(parent.run_dir, "REQUEST.json", {}) or {}
    from_profile = str(request_doc.get("profile") or "lite")
    to_profile = args.to
    if from_profile not in PROFILE_ORDER or PROFILE_ORDER.index(to_profile) <= PROFILE_ORDER.index(from_profile):
        print(f"Invalid upward escalation {from_profile} -> {to_profile}", file=sys.stderr)
        return 2
    last_report = ArtifactStore.read_json(parent.run_dir, "FINAL_REPORT.json", {}) or {}
    child = create_escalation_child(
        target,
        parent.run_id,
        to_profile,
        failures=(last_report.get("gate") or {}).get("failures", []),
    )
    payload = {
        "parent_run_id": parent.run_id,
        "run_id": child.run_id,
        "run_dir": str(child.run_dir),
        "profile": to_profile,
        "fresh_child": True,
        "evidence_inherited_as_proof": False,
    }
    print(json.dumps(payload, indent=2))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="factory", description="Adaptive Agent Harness — LITE / PRO / FACTORY")
    sub = parser.add_subparsers(dest="cmd", required=True)

    setup_parser = sub.add_parser("setup")
    setup_parser.add_argument("--target")
    setup_parser.add_argument("--non-interactive", action="store_true")
    setup_parser.set_defaults(func=setup)

    doctor_parser = sub.add_parser("doctor")
    doctor_parser.add_argument("--target")
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.set_defaults(func=doctor)

    run_parser = sub.add_parser("run")
    run_parser.add_argument("request")
    run_parser.add_argument("--target")
    run_parser.add_argument("--profile", choices=["auto", "lite", "pro", "factory"], default="auto")
    run_parser.add_argument("--guardian", choices=["auto", "open", "guarded", "locked"], default="auto")
    run_parser.add_argument("--domain", choices=["code", "content", "research", "operations"], default="code")
    run_parser.set_defaults(func=run_cmd)

    for name, func in [("status", status), ("resume", resume), ("eval", eval_cmd), ("fix", fix_cmd), ("report", report)]:
        item = sub.add_parser(name)
        item.add_argument("run_id", nargs="?")
        item.add_argument("--target")
        item.set_defaults(func=func)

    rollback_parser = sub.add_parser("rollback")
    rollback_parser.add_argument("run_id", nargs="?")
    rollback_parser.add_argument("--target")
    rollback_parser.add_argument("--apply", action="store_true")
    rollback_parser.add_argument("--force-dirty-baseline", action="store_true")
    rollback_parser.set_defaults(func=rollback)

    init_parser = sub.add_parser("init-run")
    init_parser.add_argument("request")
    init_parser.add_argument("--target")
    init_parser.add_argument("--profile", choices=["auto", "lite", "pro", "factory"], default="auto")
    init_parser.add_argument("--guardian", choices=["auto", "open", "guarded", "locked"], default="auto")
    init_parser.add_argument("--domain", choices=["code", "content", "research", "operations"], default="code")
    init_parser.add_argument("--json", action="store_true")
    init_parser.set_defaults(func=init_run)

    seal_parser = sub.add_parser("seal-rubric")
    seal_parser.add_argument("run_id", nargs="?")
    seal_parser.add_argument("--target")
    seal_parser.set_defaults(func=seal_rubric_cmd)

    gate_parser = sub.add_parser("gate")
    gate_parser.add_argument("run_id", nargs="?")
    gate_parser.add_argument("--target")
    gate_parser.set_defaults(func=gate_cmd)

    escalation = sub.add_parser("escalate")
    escalation.add_argument("run_id")
    escalation.add_argument("--to", required=True, choices=["pro", "factory"])
    escalation.add_argument("--target")
    escalation.set_defaults(func=escalate_cmd)
    return parser


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
        return int(args.func(args))
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"AAH error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
