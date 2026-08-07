from __future__ import annotations
import os, re
from typing import Mapping, Any

SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|PRIVATE|CREDENTIAL|COOKIE|SESSION)", re.I)

class EnvRouter:
    API_KEYS = {"ANTHROPIC_API_KEY", "OPENAI_API_KEY"}
    REVIEW_ROLES = {"planner","architect","tester","evaluator","task_evaluator","system_tester","content_evaluator","fact_checker","security_reviewer","final_reviewer"}

    def __init__(self, subscription_only: bool = True): self.subscription_only = subscription_only

    def sanitize_provider_env(self, source: Mapping[str, str] | None = None) -> dict[str, str]:
        env = dict(source or os.environ)
        if self.subscription_only:
            for key in self.API_KEYS: env.pop(key, None)
        return env

    @staticmethod
    def classify_name(name: str) -> str: return "secret" if SECRET_NAME.search(name) else "config"

    def scoped_provider_env(self, project: dict[str,Any], role: str, task: dict[str,Any], source: Mapping[str,str]|None=None) -> dict[str,str]:
        env=self.sanitize_provider_env(source)
        names=set(project.get("env_names") or []); classes=project.get("env_classes") or {}
        explicit=set(task.get("required_env") or [])
        # Remove project-specific variables from provider subprocess unless permitted.
        for name in names:
            secret=classes.get(name)=="secret"
            allowed=(not secret) or (name in explicit and role not in self.REVIEW_ROLES)
            if not allowed: env.pop(name,None)
        return env
