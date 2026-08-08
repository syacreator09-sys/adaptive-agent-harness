import unittest
from factory.envs import EnvRouter


class EnvRouterTests(unittest.TestCase):
    def test_subscription_mode_removes_provider_api_credentials(self):
        source = {
            "ANTHROPIC_API_KEY": "paid-a",
            "ANTHROPIC_AUTH_TOKEN": "paid-b",
            "OPENAI_API_KEY": "paid-c",
            "PATH": "/bin",
        }
        env = EnvRouter(True).sanitize_provider_env(source)
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", env)
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertEqual(env["PATH"], "/bin")

    def test_reviewers_never_receive_project_secret_even_if_task_requests_it(self):
        project = {"env_names": ["DATABASE_URL"], "env_classes": {"DATABASE_URL": "secret"}}
        source = {"DATABASE_URL": "postgres://secret", "PATH": "/bin"}
        env = EnvRouter().scoped_provider_env(project, "evaluator", {"required_env": ["DATABASE_URL"]}, source)
        self.assertNotIn("DATABASE_URL", env)

    def test_builder_receives_discovered_secret_only_when_explicitly_requested(self):
        project = {"env_names": ["DATABASE_URL"], "env_classes": {"DATABASE_URL": "secret"}}
        source = {"DATABASE_URL": "postgres://secret", "PATH": "/bin"}
        router = EnvRouter()
        denied = router.scoped_provider_env(project, "builder", {}, source)
        allowed = router.scoped_provider_env(project, "builder", {"required_env": ["DATABASE_URL"]}, source)
        self.assertNotIn("DATABASE_URL", denied)
        self.assertEqual(allowed["DATABASE_URL"], "postgres://secret")

    def test_unknown_ambient_secret_is_removed_even_if_task_requests_it(self):
        project = {"env_names": [], "env_classes": {}}
        source = {"DATABASE_URL": "ambient-secret", "PATH": "/bin"}
        env = EnvRouter().scoped_provider_env(project, "builder", {"required_env": ["DATABASE_URL"]}, source)
        self.assertNotIn("DATABASE_URL", env)

    def test_safe_ambient_auth_socket_is_preserved(self):
        project = {"env_names": [], "env_classes": {}}
        source = {"SSH_AUTH_SOCK": "/tmp/agent.sock", "PATH": "/bin"}
        env = EnvRouter().scoped_provider_env(project, "evaluator", {}, source)
        self.assertEqual(env["SSH_AUTH_SOCK"], "/tmp/agent.sock")


if __name__ == "__main__":
    unittest.main()
