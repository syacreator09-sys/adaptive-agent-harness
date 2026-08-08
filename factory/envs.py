from __future__ import annotations
import os
import re
from typing import Mapping, Any


SECRET_NAME = re.compile(
    r"(API[_-]?KEY|TOKEN|SECRET|PASSWORD|PASSWD|PRIVATE|CREDENTIAL|COOKIE|SESSION|AUTH|JWT|DATABASE_URL|REDIS_URL|DSN|CONNECTION_STRING)",
    re.I,
)
_SAFE_AMBIENT = {"SSH_AUTH_SOCK"}


class EnvRouter:
    API_KEYS = {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY"}
    REVIEW_ROLES = {
        "planner", "architect", "tester", "evaluator", "task_evaluator", "system_tester",
        "content_strategist", "content_evaluator", "fact_checker", "security_reviewer",
        "final_reviewer",
    }

    def __init__(self, subscription_only: bool = True):
        self.subscription_only = subscription_only

    def sanitize_provider_env(self, source: Mapping[str, str] | None = None) -> dict[str, str]:
        env = dict(source or os.environ)
        if self.subscription_only:
            for key in self.API_KEYS:
                env.pop(key, None)
        return env

    @staticmethod
    def classify_name(name: str) -> str:
        if name in _SAFE_AMBIENT:
            return "config"
        return "secret" if SECRET_NAME.search(name) else "config"

    def scoped_provider_env(
        self,
        project: dict[str, Any],
        role: str,
        task: dict[str, Any],
        source: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        source_env = dict(source or os.environ)
        env = self.sanitize_provider_env(source_env)
        names = set(project.get("env_names") or [])
        classes = project.get("env_classes") or {}
        explicit = set(task.get("required_env") or []) & names

        # Fail closed for ambient secrets too: reviewers never receive them and
        # producers receive only project-known names explicitly requested by the
        # task. This prevents a shell's unrelated DATABASE_URL/GITHUB_TOKEN/etc.
        # from leaking into an agent just because it happened to be exported.
        for name in list(env):
            if self.classify_name(name) == "secret":
                env.pop(name, None)

        if role not in self.REVIEW_ROLES:
            for name in explicit:
                secret = classes.get(name) == "secret" or self.classify_name(name) == "secret"
                if not secret:
                    continue
                if self.subscription_only and name in self.API_KEYS:
                    continue
                if name in source_env:
                    env[name] = source_env[name]
        return env
