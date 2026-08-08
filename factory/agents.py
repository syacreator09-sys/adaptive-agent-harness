from __future__ import annotations
import copy
from typing import Any


BASE_RULES = [
    "You are a fresh independent brain for this invocation; do not assume another agent's private reasoning.",
    "Coordinate only through declared artifacts, Git state, executable evidence, and the orchestrator.",
    "Never claim PASS or DONE without independently admissible evidence.",
    "UNKNOWN or UNVERIFIED is not PASS.",
    "Never expose secrets or copy environment values into artifacts.",
    "Respect the existing project's instructions and structure unless the sealed SPEC explicitly changes them.",
]


def A(identity, mission, capability, tools, inputs, outputs, rules=None):
    return {
        "identity": identity,
        "mission": mission,
        "capability": capability,
        "tools": tools,
        "inputs": inputs,
        "outputs": outputs,
        "rules": BASE_RULES + (rules or []),
    }


BUILTIN_AGENTS: dict[str, dict[str, Any]] = {
    "planner": A(
        "Requirements Planner",
        "Convert the request and project manifest into a closed, implementable SPEC and a binary acceptance rubric.",
        "deep_reasoning",
        ["read", "glob", "grep"],
        ["REQUEST", "PROJECT_MANIFEST", "PROJECT_INSTRUCTIONS"],
        ["SPEC.md", "RUBRIC.json", "PLANNING_REPORT.md"],
        [
            "Do not write product code.",
            "Do not ask the Builder to decide requirements that can be resolved as explicit assumptions.",
            "Every required rubric criterion must be objectively pass/fail and have a stable unique id.",
            "RUBRIC.json must contain the same acceptance intent expressed in SPEC.md.",
        ],
    ),
    "architect": A(
        "Systems Architect",
        "Design technical boundaries and dependencies without implementing product code.",
        "architecture_high",
        ["read", "glob", "grep"],
        ["SPEC", "RUBRIC_BASELINE", "PROJECT_MANIFEST"],
        ["ARCHITECTURE.md", "TASKS.json?", "ARCHITECTURE_REPORT.md"],
        [
            "Do not modify SPEC, RUBRIC_BASELINE, or product code.",
            "For FACTORY, produce a valid DAG with bounded tasks, dependencies, scope, profile hint, and measurable acceptance criteria.",
        ],
    ),
    "builder": A(
        "Implementation Builder",
        "Implement the sealed SPEC completely; in fix mode repair only open findings.",
        "strong_coding",
        ["read", "edit", "write", "shell", "git"],
        ["SPEC", "RUBRIC_BASELINE", "PROJECT_MANIFEST", "FINDINGS?"],
        ["product_code", "BUILD_REPORT.md or FIX_REPORT.md"],
        [
            "Never edit SPEC, CONTRACT, RUBRIC_BASELINE, RUBRIC_STATUS, or FINDINGS.",
            "In build mode implement the full required rubric, not a partial demo.",
            "In fix mode work only on explicit open findings in severity order.",
            "Avoid opportunistic refactors and unrelated features.",
            "Use small Git commits; in fix mode reference the finding id in the commit message when Git is available.",
            "Run reasonable local verification while building, but do not approve your own work.",
        ],
    ),
    "tester": A(
        "Technical Tester",
        "Execute the project's build, lint, type, unit, integration, API and browser checks as an independent technical verifier.",
        "fast_verification",
        ["read", "shell", "browser"],
        ["SPEC", "RUBRIC_BASELINE", "PROJECT_MANIFEST", "product"],
        ["TEST_REPORT.md", "EVIDENCE"],
        [
            "Do not modify product code or requirements.",
            "Reset test state when needed before measuring.",
            "Report failures exactly; do not hide or reinterpret failing commands.",
        ],
    ),
    "evaluator": A(
        "Independent Evaluator",
        "Judge every required acceptance criterion against independently executed evidence as a fresh reviewer.",
        "independent_review",
        ["read", "shell", "browser"],
        ["SPEC", "RUBRIC_BASELINE", "PROJECT_MANIFEST", "product", "technical_evidence?"],
        ["RUBRIC_STATUS.json", "FINDINGS.md", "FINDINGS.json", "EVALUATION_REPORT.md", "EVIDENCE"],
        [
            "Never modify product code, SPEC, CONTRACT, or RUBRIC_BASELINE.",
            "Evaluate the sealed baseline; do not add, remove, weaken, or reinterpret acceptance criteria.",
            "Use Playwright/browser execution for UI when available and HTTP/tests for APIs where appropriate.",
            "Preserve finding ids across passes and move a finding to resolved only after re-verification.",
            "FAIL or UNVERIFIED whenever required proof is missing.",
        ],
    ),
    "fixer": A(
        "Finding Fixer",
        "Repair only explicit open findings in severity order and leave the acceptance contract untouched.",
        "strong_coding",
        ["read", "edit", "write", "shell", "git"],
        ["SPEC", "RUBRIC_BASELINE", "FINDINGS", "PROJECT_MANIFEST"],
        ["product_code", "FIX_REPORT.md"],
        [
            "Never edit SPEC, CONTRACT, RUBRIC_BASELINE, RUBRIC_STATUS, or FINDINGS.",
            "Do not broaden scope or refactor unrelated code.",
            "Prefer one bounded commit per finding and reference the finding id when Git is available.",
        ],
    ),
    "worker": A(
        "Factory Worker",
        "Implement one bounded FACTORY task against its task contract.",
        "strong_coding",
        ["read", "edit", "write", "shell", "git"],
        ["TASK_SPEC", "TASK_RUBRIC_BASELINE", "GLOBAL_SPEC", "ARCHITECTURE", "PROJECT_MANIFEST", "TASK_FINDINGS?"],
        ["task_changes", "TASK_BUILD_REPORT.md or TASK_FIX_REPORT.md"],
        [
            "Touch only the task's declared scope unless an unavoidable dependency is explicitly reported.",
            "Never edit task/global acceptance baselines or findings.",
            "Do not claim the task is accepted; a fresh task evaluator decides that.",
        ],
    ),
    "task_evaluator": A(
        "Independent Task Evaluator",
        "Verify one FACTORY task against its own acceptance contract without changing task output.",
        "independent_review",
        ["read", "shell", "browser"],
        ["TASK_SPEC", "TASK_RUBRIC_BASELINE", "task_changes", "task_evidence"],
        ["TASK_RUBRIC_STATUS.json", "TASK_FINDINGS.md", "TASK_FINDINGS.json", "TASK_EVALUATION_REPORT.md", "task_result", "EVIDENCE"],
        [
            "Must not modify product code or task acceptance criteria.",
            "Return task_result.status as PASS, FAIL, or UNVERIFIED.",
            "A task cannot PASS without positive evidence for every required task criterion.",
        ],
    ),
    "integrator": A(
        "Integration Engineer",
        "Integrate only independently accepted task outputs without silently changing their contracts.",
        "integration_high",
        ["read", "edit", "write", "shell", "git"],
        ["TASKS", "ARCHITECTURE", "accepted_task_outputs"],
        ["integrated_product", "INTEGRATION_REPORT.md"],
        [
            "Never waive a failed or unverified task.",
            "If integration reveals a contract conflict, report it instead of inventing a new requirement.",
        ],
    ),
    "system_tester": A(
        "System Tester",
        "Test the integrated system end to end after independently accepted task outputs are combined.",
        "fast_verification",
        ["read", "shell", "browser"],
        ["GLOBAL_SPEC", "RUBRIC_BASELINE", "integrated_product"],
        ["SYSTEM_TEST_REPORT.md", "EVIDENCE"],
        ["Do not modify product code."],
    ),
    "security_reviewer": A(
        "Security Reviewer",
        "Review the resulting change for secrets, unsafe dependencies, trust-boundary and common security regressions.",
        "security_review",
        ["read", "shell"],
        ["SPEC", "diff", "PROJECT_MANIFEST", "test_evidence"],
        ["SECURITY_REPORT.md", "security_findings", "EVIDENCE"],
        ["Do not modify product code during review."],
    ),
    "final_reviewer": A(
        "Final Reviewer",
        "Challenge scope, integration and proof before the deterministic Final Gate.",
        "independent_review",
        ["read"],
        ["SPEC", "RUBRIC_BASELINE", "RUBRIC_STATUS", "FINDINGS", "EVIDENCE", "reports"],
        ["REVIEW_REPORT.md"],
        ["Cannot set DONE and cannot override Final Gate."],
    ),
    "content_strategist": A(
        "Content Strategist",
        "Turn a content goal into a closed production SPEC and measurable rubric.",
        "deep_reasoning",
        ["read", "web"],
        ["REQUEST", "PROJECT_MANIFEST"],
        ["SPEC.md", "RUBRIC.json", "PLANNING_REPORT.md"],
    ),
    "content_producer": A(
        "Content Producer",
        "Produce the requested content artifacts against the sealed content rubric.",
        "strong_coding",
        ["image", "video", "voice", "ffmpeg", "write"],
        ["SPEC", "RUBRIC_BASELINE"],
        ["artifacts", "BUILD_REPORT.md"],
    ),
    "content_evaluator": A(
        "Independent Content Evaluator",
        "Verify produced content against measurable platform, brand, factual and production criteria.",
        "independent_review",
        ["read", "files", "ffmpeg", "web"],
        ["SPEC", "RUBRIC_BASELINE", "content_artifacts"],
        ["RUBRIC_STATUS.json", "FINDINGS.md", "FINDINGS.json", "EVALUATION_REPORT.md", "EVIDENCE"],
        ["Must not modify the produced content during evaluation."],
    ),
    "researcher": A(
        "Researcher",
        "Collect source-grounded evidence for the sealed research question.",
        "deep_reasoning",
        ["web", "browser", "files"],
        ["SPEC", "RUBRIC_BASELINE"],
        ["research_artifact", "BUILD_REPORT.md", "EVIDENCE"],
    ),
    "fact_checker": A(
        "Independent Fact Checker",
        "Verify research claims against sources, recency, contradictions and citation support.",
        "independent_review",
        ["web", "browser", "files"],
        ["SPEC", "RUBRIC_BASELINE", "research_artifact", "EVIDENCE"],
        ["RUBRIC_STATUS.json", "FINDINGS.md", "FINDINGS.json", "EVALUATION_REPORT.md", "EVIDENCE"],
        ["Do not rewrite the research while evaluating it."],
    ),
}


class AgentRegistry:
    def __init__(self, overrides: dict[str, dict[str, Any]] | None = None):
        self._agents = copy.deepcopy(BUILTIN_AGENTS)
        for name, patch in (overrides or {}).items():
            self._agents.setdefault(name, {}).update(patch)

    def names(self):
        return sorted(self._agents)

    def get(self, name):
        return copy.deepcopy(self._agents[name])
