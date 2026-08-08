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

    def test_unknown_requested_secret_name_is_not_added(self):
        project = {"env_names": [], "env_classes": {}}
        source = {"DATABASE_URL": "ambient-secret", "PATH": "/bin"}
        env = EnvRouter().scoped_provider_env(project, "builder", {"required_env": ["DATABASE_URL"]}, source)
        # Project Adapter did not discover this as a project env, so AAH does not
        # claim permission to grant it. Ambient process variables outside the
        # project manifest are not managed here; subscription API keys are still stripped.
        self.assertEqual(env["DATABASE_URL"], "ambient-secret")


if __name__ == "__main__":
    unittest.main()
