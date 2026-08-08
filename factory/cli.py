from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path
from .config import AAHConfig
from .project_adapter import ProjectAdapter
from .providers import ProviderRegistry
from .tools import ToolRegistry
from .router import AdaptiveRouter
from .agents import AgentRegistry
from .executor import AgentExecutor
from .artifacts import ArtifactStore
from .profiles import LiteRunner, ProRunner, FactoryRunner
from .orchestrator import AutoOrchestrator
from .domains import role_for
from .final_gate import FinalGate
from .codex_profiles import install_profiles


def _target(args)->Path:
    return Path(getattr(args,"target",None) or os.getcwd()).resolve()


def _ask_choice(label, choices, default):
    if not sys.stdin.isatty():
        return default
    raw=input(f"{label} [{'/'.join(choices)}] (default {default}): ").strip().lower()
    return raw if raw in choices else default


def setup(args):
    target=_target(args)
    target.mkdir(parents=True,exist_ok=True)
    aah=target/".aah"
    aah.mkdir(exist_ok=True)
    manifest=ProjectAdapter(target).inspect()
    providers=ProviderRegistry.discover()
    tools=ToolRegistry.discover()
    (aah/"project.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    (aah/"capabilities.json").write_text(json.dumps({"providers":providers,"tools":tools},indent=2)+"\n",encoding="utf-8")
    if providers.get("codex",{}).get("available"):
        codex_permissions=install_profiles(target)
    else:
        codex_permissions={"installed":False,"reason":"codex_unavailable"}

    cfg=AAHConfig.load(target)
    if not args.non_interactive:
        available=[k for k,v in providers.items() if v.get("available") and v.get("authenticated") is not False]
        suggested="both" if len(available)>1 else available[0] if available else "auto"
        cfg.data["providers"]["strategy"]=_ask_choice("Provider strategy",["auto","claude","codex","both"],suggested)
        cfg.data["models"]["policy"]=_ask_choice("Model policy",["quality","balanced","economy"],cfg.data["models"]["policy"])
        cfg.data["execution"]["profile"]=_ask_choice("Default profile",["auto","lite","pro","factory"],cfg.data["execution"]["profile"])
        cfg.data["guardian"]["mode"]=_ask_choice("Guardian",["auto","open","guarded","locked"],cfg.data["guardian"]["mode"])
        cfg.data["billing"]={"mode":"subscription_only","api_fallback":False}
    cfg.save(target)

    gi=target/".gitignore"
    text=gi.read_text(encoding="utf-8",errors="ignore") if gi.exists() else ""
    if ".aah/" not in text.splitlines():
        gi.write_text(text+("\n" if text and not text.endswith("\n") else "")+".aah/\n",encoding="utf-8")
    print(json.dumps({
        "ok":True,
        "target":str(target),
        "stacks":manifest["stacks"],
        "providers":providers,
        "codex_permissions":codex_permissions,
        "config":str(aah/"factory.local.yaml"),
    },indent=2))
    return 0


def doctor(args):
    target=_target(args)
    cfg=AAHConfig.load(target)
    providers=ProviderRegistry.discover()
    tools=ToolRegistry.discover()
    project=ProjectAdapter(target).inspect()
    ready=any(v.get("available") and v.get("authenticated") is not False for v in providers.values())
    payload={"ok":ready,"target":str(target),"providers":providers,"tools":tools,"project":project,"billing":cfg.data["billing"]}
    if args.json:
        print(json.dumps(payload,indent=2))
    else:
        print(f"AAH doctor: {target}")
        print("Providers: "+", ".join(f"{k}=installed:{'yes' if v['available'] else 'no'},auth:{'yes' if v.get('authenticated') is True else 'no' if v.get('authenticated') is False else 'unknown'}" for k,v in providers.items()))
        print("Stacks: "+(", ".join(project["stacks"]) or "unknown"))
        print("Billing: "+cfg.data["billing"]["mode"])
        print("Ready: "+("yes" if ready else "no"))
    return 0 if ready else 3


def _runner(target,profile,executor):
    return {"lite":LiteRunner,"pro":ProRunner,"factory":FactoryRunner}[profile](target,executor)


def _roles_for(profile:str,domain:str)->list[str]:
    canonical={
      "lite":["planner","builder","evaluator"],
      "pro":["planner","architect","builder","tester","evaluator","fixer"],
      "factory":["planner","architect","worker","tester","task_evaluator","fixer","integrator","system_tester","evaluator","security_reviewer","final_reviewer"],
    }[profile]
    roles=[]
    for role in canonical:
        if role in {"planner","builder","tester","evaluator","fixer","worker"}:
            actual=role_for(domain,role)
        elif role=="system_tester" and domain!="code":
            actual=role_for(domain,"tester")
        else:
            actual=role
        if actual not in roles:
            roles.append(actual)
    return roles


def _configured_providers(cfg, discovered):
    strategy=cfg.data.get("providers",{}).get("strategy","auto")
    if strategy=="claude":
        return {"claude":discovered.get("claude",{"available":False}),"codex":{"available":False,"reason":"disabled_by_config"}}
    if strategy=="codex":
        return {"claude":{"available":False,"reason":"disabled_by_config"},"codex":discovered.get("codex",{"available":False})}
    return discovered


def _require_router(target, cfg):
    providers=_configured_providers(cfg,ProviderRegistry.discover())
    router=AdaptiveRouter(providers)
    if router.available():
        return router
    installed=[k for k,v in providers.items() if v.get("available")]
    if installed:
        raise RuntimeError("Provider CLI detected but no authenticated subscription session is ready. Login to Claude Code/Codex, then run factory doctor.")
    raise RuntimeError("No provider CLI detected. Install/login to Claude Code or Codex, then run factory doctor.")


def run_cmd(args):
    target=_target(args)
    cfg=AAHConfig.load(target)
    router=_require_router(target,cfg)

    def executor_factory(profile,domain):
        roles=_roles_for(profile,domain)
        assignments=router.assign_roles(roles,cfg.data["models"]["policy"],cfg.data["models"].get("overrides"))
        return AgentExecutor(target,assignments,subscription_only=cfg.data["billing"]["mode"]=="subscription_only",registry=AgentRegistry())

    requested_profile=args.profile
    if requested_profile=="auto" and cfg.data["execution"].get("profile","auto")!="auto":
        requested_profile=cfg.data["execution"]["profile"]
    requested_guardian=args.guardian
    if requested_guardian=="auto" and cfg.data["guardian"].get("mode","auto")!="auto":
        requested_guardian=cfg.data["guardian"]["mode"]
    result=AutoOrchestrator(target,executor_factory,router).run(args.request,domain=args.domain,profile=requested_profile,guardian=requested_guardian)
    print(json.dumps(result,indent=2))
    return 0 if result["done"] else 2


def _resolve_run(target,run_id):
    store=ArtifactStore(target)
    return store.get_run(run_id) if run_id else store.latest_run()


def status(args):
    target=_target(args); run=_resolve_run(target,args.run_id)
    if not run:
        print("No runs",file=sys.stderr); return 1
    state=ArtifactStore.read_json(run.run_dir,"STATE.json",{})
    print(json.dumps(state,indent=2)); return 0


def report(args):
    target=_target(args); run=_resolve_run(target,args.run_id)
    if not run:
        print("No runs",file=sys.stderr); return 1
    p=run.run_dir/"FINAL_REPORT.md"
    print(p.read_text(encoding="utf-8") if p.exists() else json.dumps(ArtifactStore.read_json(run.run_dir,"FINAL_REPORT.json",{}),indent=2))
    return 0


def resume(args):
    target=_target(args); run=_resolve_run(target,args.run_id)
    if not run:
        print("Run not found",file=sys.stderr); return 1
    req=ArtifactStore.read_json(run.run_dir,"REQUEST.json",{})
    profile=req.get("profile","lite"); guardian=req.get("guardian","guarded")
    cfg=AAHConfig.load(target); router=_require_router(target,cfg)
    roles=_roles_for(profile,req.get("domain","code"))
    ex=AgentExecutor(target,router.assign_roles(roles,cfg.data["models"]["policy"],cfg.data["models"].get("overrides")),cfg.data["billing"]["mode"]=="subscription_only")
    result=_runner(target,profile,ex).run(req.get("request","resume"),guardian=guardian,domain=req.get("domain","code"),run_id=run.run_id)
    print(json.dumps(result,indent=2)); return 0 if result["done"] else 2


def _one_step_executor(target,profile,domain):
    cfg=AAHConfig.load(target); router=_require_router(target,cfg); roles=_roles_for(profile,domain)
    return AgentExecutor(target,router.assign_roles(roles,cfg.data["models"]["policy"],cfg.data["models"].get("overrides")),cfg.data["billing"]["mode"]=="subscription_only")


def eval_cmd(args):
    target=_target(args); run=_resolve_run(target,args.run_id)
    if not run:
        print("Run not found",file=sys.stderr); return 1
    req=ArtifactStore.read_json(run.run_dir,"REQUEST.json",{})
    domain=req.get("domain","code"); profile=req.get("profile","lite"); guardian=req.get("guardian","guarded")
    ex=_one_step_executor(target,profile,domain); runner=_runner(target,profile,ex); ctx=runner._context(run,guardian)
    role=role_for(domain,"evaluator")
    runner._ingest(run,ex.execute(role,{"mode":"evaluate_only"},ctx))
    gate=runner._gate(run); report=runner._write_report(run,gate,{"manual_eval":True})
    print(json.dumps(report,indent=2)); return 0 if gate["done"] else 2


def fix_cmd(args):
    target=_target(args); run=_resolve_run(target,args.run_id)
    if not run:
        print("Run not found",file=sys.stderr); return 1
    req=ArtifactStore.read_json(run.run_dir,"REQUEST.json",{})
    domain=req.get("domain","code"); profile=req.get("profile","lite"); guardian=req.get("guardian","guarded")
    ex=_one_step_executor(target,profile,domain); runner=_runner(target,profile,ex); ctx=runner._context(run,guardian)
    canonical="builder" if profile=="lite" else "fixer"
    role=role_for(domain,canonical)
    runner._ingest(run,ex.execute(role,{"mode":"fix_only","findings":runner._findings(run)},ctx))
    eval_role=role_for(domain,"evaluator")
    runner._ingest(run,ex.execute(eval_role,{"mode":"evaluate_after_fix"},ctx))
    gate=runner._gate(run); report=runner._write_report(run,gate,{"manual_fix":True})
    print(json.dumps(report,indent=2)); return 0 if gate["done"] else 2


def rollback(args):
    target=_target(args); run=_resolve_run(target,args.run_id)
    if not run:
        print("Run not found",file=sys.stderr); return 1
    state=ArtifactStore.read_json(run.run_dir,"STATE.json",{})
    base=state.get("git_base") or ArtifactStore.read_json(run.run_dir,"REQUEST.json",{}).get("git_base")
    if not base:
        print("No recorded git checkpoint; rollback refused.",file=sys.stderr); return 2
    if state.get("git_base_dirty") and not args.force_dirty_baseline:
        print("Rollback refused: the project already had tracked/untracked changes at AAH start. Commit/stash them first, or re-run with --force-dirty-baseline if you explicitly accept losing tracked baseline edits.",file=sys.stderr)
        return 2
    if not args.apply:
        print(f"Dry run: would restore tracked files from {base}. Re-run with --apply.")
        return 0
    cp=subprocess.run(["git","-C",str(target),"restore","--source",base,"--staged","--worktree","."],text=True,capture_output=True)
    if cp.returncode:
        print(cp.stderr,file=sys.stderr); return cp.returncode
    print(f"Restored tracked files from {base}; untracked files were preserved.")
    return 0


def init_run(args):
    target=_target(args)
    route=AdaptiveRouter(ProviderRegistry.discover()).route(args.request)
    profile=args.profile if args.profile!="auto" else route["profile"]
    guardian=args.guardian if args.guardian!="auto" else route["guardian"]
    run=ArtifactStore(target).create_run(args.request,profile,guardian,args.domain)
    payload={"run_id":run.run_id,"run_dir":str(run.run_dir),"profile":profile,"guardian":guardian,"route":route}
    print(json.dumps(payload) if args.json else json.dumps(payload,indent=2)); return 0


def gate_cmd(args):
    target=_target(args); run=_resolve_run(target,args.run_id)
    if not run:
        print("Run not found",file=sys.stderr); return 1
    rubric=ArtifactStore.read_json(run.run_dir,"RUBRIC.json",[])
    findings=ArtifactStore.read_json(run.run_dir,"FINDINGS.json",[])
    result=FinalGate(run.run_dir).evaluate(rubric,findings)
    print(json.dumps(result,indent=2)); return 0 if result["done"] else 2


def build_parser():
    p=argparse.ArgumentParser(prog="factory",description="Adaptive Agent Harness — LITE / PRO / FACTORY")
    sub=p.add_subparsers(dest="cmd",required=True)
    s=sub.add_parser("setup"); s.add_argument("--target"); s.add_argument("--non-interactive",action="store_true"); s.set_defaults(func=setup)
    d=sub.add_parser("doctor"); d.add_argument("--target"); d.add_argument("--json",action="store_true"); d.set_defaults(func=doctor)
    r=sub.add_parser("run"); r.add_argument("request"); r.add_argument("--target"); r.add_argument("--profile",choices=["auto","lite","pro","factory"],default="auto"); r.add_argument("--guardian",choices=["auto","open","guarded","locked"],default="auto"); r.add_argument("--domain",choices=["code","content","research","operations"],default="code"); r.set_defaults(func=run_cmd)
    for name,func in [("status",status),("resume",resume),("eval",eval_cmd),("fix",fix_cmd),("report",report)]:
        x=sub.add_parser(name); x.add_argument("run_id",nargs="?"); x.add_argument("--target"); x.set_defaults(func=func)
    rb=sub.add_parser("rollback"); rb.add_argument("run_id",nargs="?"); rb.add_argument("--target"); rb.add_argument("--apply",action="store_true"); rb.add_argument("--force-dirty-baseline",action="store_true"); rb.set_defaults(func=rollback)
    ir=sub.add_parser("init-run"); ir.add_argument("request"); ir.add_argument("--target"); ir.add_argument("--profile",choices=["auto","lite","pro","factory"],default="auto"); ir.add_argument("--guardian",choices=["auto","open","guarded","locked"],default="auto"); ir.add_argument("--domain",choices=["code","content","research","operations"],default="code"); ir.add_argument("--json",action="store_true"); ir.set_defaults(func=init_run)
    g=sub.add_parser("gate"); g.add_argument("run_id",nargs="?"); g.add_argument("--target"); g.set_defaults(func=gate_cmd)
    return p


def main(argv=None):
    try:
        args=build_parser().parse_args(argv)
        return args.func(args)
    except (RuntimeError,ValueError,FileNotFoundError,KeyError) as exc:
        print(f"AAH error: {exc}",file=sys.stderr)
        return 3


if __name__=="__main__":
    raise SystemExit(main())
