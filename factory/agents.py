from __future__ import annotations
import copy
from typing import Any

BASE_RULES=[
    "Coordinate only through declared artifacts and the orchestrator.",
    "Never claim PASS without admissible evidence.",
    "Evidence that supports PASS must contain an explicit ok:true result and a stable id or type reference.",
    "Do not expose secrets or copy environment values into artifacts.",
    "Respect the existing project's instructions and structure unless the SPEC explicitly changes them.",
]


def A(identity, mission, capability, tools, inputs, outputs, rules=None, required_tools=None):
    return {
        "identity":identity,
        "mission":mission,
        "capability":capability,
        "tools":tools,
        "required_tools":required_tools or [],
        "inputs":inputs,
        "outputs":outputs,
        "rules":BASE_RULES+(rules or []),
    }


BUILTIN_AGENTS: dict[str,dict[str,Any]]={
 "planner":A("Requirements Planner","Turn the request and project manifest into a closed SPEC and binary evidence rubric.","deep_reasoning",["read","glob","grep"],["REQUEST","PROJECT_MANIFEST"],["SPEC.md","RUBRIC.json"],["Do not write product code.","Resolve non-critical ambiguity as explicit assumptions."]),
 "architect":A("Systems Architect","Design boundaries, interfaces, dependencies and, for FACTORY, a valid task DAG.","deep_reasoning",["read","glob","grep"],["SPEC","PROJECT_MANIFEST"],["ARCHITECTURE.md","TASKS.json"],["Do not implement product code.","FACTORY tasks must have unique id, profile lite/pro, depends_on list, and non-empty measurable acceptance criteria."]),
 "builder":A("Implementation Builder","Implement the SPEC completely and verify while building.","strong_coding",["read","edit","write","shell","git"],["SPEC","RUBRIC","PROJECT_MANIFEST","FINDINGS?"],["product_code","build_summary"],["Never edit SPEC or FINDINGS.","When findings exist, make surgical fixes only."]),
 "tester":A("Technical Tester","Execute build, lint, type, unit, integration, API and browser checks supported by the project.","fast_verification",["read","shell","browser"],["SPEC","RUBRIC","PROJECT_MANIFEST"],["EVIDENCE"],["Do not change requirements.","Do not hide failing tests.","Emit at least one evidence record with type technical_test and explicit ok:true/false for the executed technical gate."]),
 "evaluator":A("Independent Evaluator","Judge every rubric criterion from execution evidence as a fresh reviewer.","independent_review",["read","shell","browser"],["SPEC","RUBRIC","PROJECT_MANIFEST"],["RUBRIC.json","FINDINGS.json","EVIDENCE"],["Must not modify product code.","FAIL or UNVERIFIED when proof is missing."]),
 "fixer":A("Finding Fixer","Repair only explicit open findings in severity order.","strong_coding",["read","edit","write","shell","git"],["SPEC","FINDINGS","PROJECT_MANIFEST"],["product_code","fix_summary"],["Never broaden scope or refactor unrelated code."]),
 "worker":A("Factory Worker","Complete one bounded task from the task graph and its acceptance criteria.","strong_coding",["read","edit","write","shell","git"],["TASK","SPEC","ARCHITECTURE","PROJECT_MANIFEST"],["task_changes","task_summary"],["Touch only the task's declared scope."]),
 "integrator":A("Integration Engineer","Integrate completed task outputs without silently changing task contracts.","strong_coding",["read","edit","write","shell","git"],["TASKS","ARCHITECTURE","task_outputs"],["integrated_product","integration_summary"],["Do not waive failed task acceptance criteria."]),
 "task_evaluator":A("Independent Task Evaluator","Verify one FACTORY task against its acceptance criteria without changing the task output.","independent_review",["read","shell","browser"],["TASK","task_changes","task_evidence"],["task_result","EVIDENCE"],["Must not modify product code.","Return task_result.status as PASS, FAIL, or UNVERIFIED.","A PASS task_result must include explicit positive evidence.","Emit evidence with type task_verification, task_id matching the task, and explicit ok:true/false."]),
 "system_tester":A("System Tester","Test the integrated system end to end.","independent_review",["read","shell","browser"],["SPEC","RUBRIC","integrated_product"],["EVIDENCE"],["Do not modify product code.","Emit at least one evidence record with type system_test and explicit ok:true/false."]),
 "security_reviewer":A("Security Reviewer","Review the resulting change for secrets, unsafe dependencies, trust-boundary and common security regressions.","security_review",["read","shell"],["SPEC","diff","PROJECT_MANIFEST"],["EVIDENCE","security_findings"],["Do not modify product code during review.","Emit at least one evidence record with type security and explicit ok:true/false."]),
 "final_reviewer":A("Final Reviewer","Challenge completion, scope and integration before deterministic Final Gate.","independent_review",["read"],["SPEC","RUBRIC","FINDINGS","EVIDENCE"],["review_summary"],["Cannot set DONE and cannot override Final Gate."]),
 "content_strategist":A("Content Strategist","Turn a content goal into production criteria and variants.","deep_reasoning",["read","web"],["REQUEST","PROJECT_MANIFEST"],["SPEC.md","RUBRIC.json"]),
 "content_producer":A("Content Producer","Produce the requested content artifacts using only capabilities actually connected on this machine.","strong_coding",["image","video","voice","ffmpeg","write","shell"],["SPEC"],["artifacts"],["Do not claim a media artifact exists if the required media adapter is unavailable."]),
 "content_evaluator":A("Independent Content Evaluator","Verify content against measurable platform, brand, factual and production criteria.","independent_review",["read","files","media_probe","web","shell"],["SPEC","RUBRIC","content_artifacts"],["RUBRIC.json","FINDINGS.json","EVIDENCE","task_result"],["Must not modify the produced content during evaluation.","When mode is task_evaluate, return task_result.status as PASS, FAIL, or UNVERIFIED and emit type task_verification with task_id and ok."]),
 "researcher":A("Researcher","Collect source-grounded evidence for a bounded research question.","deep_reasoning",["web","files"],["SPEC"],["EVIDENCE"],["Do not fabricate sources when web access is unavailable."],["web"]),
 "fact_checker":A("Independent Fact Checker","Verify claims against sources, recency, contradictions and citation support.","independent_review",["web","files"],["SPEC","RUBRIC","EVIDENCE"],["RUBRIC.json","FINDINGS.json","EVIDENCE","task_result"],["Do not rewrite the research while evaluating it.","Do not approve claims without source access.","When mode is task_evaluate, return task_result.status as PASS, FAIL, or UNVERIFIED and emit type task_verification with task_id and ok."],["web"]),
}


class AgentRegistry:
    def __init__(self, overrides: dict[str,dict[str,Any]]|None=None):
        self._agents=copy.deepcopy(BUILTIN_AGENTS)
        for name,patch in (overrides or {}).items():
            self._agents.setdefault(name,{}).update(patch)

    def names(self):
        return sorted(self._agents)

    def get(self,name):
        return copy.deepcopy(self._agents[name])
