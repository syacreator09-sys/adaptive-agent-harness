import unittest
from factory.guardian import Guardian, Decision

class GuardianTests(unittest.TestCase):
    def test_universal_destructive_blocked_even_open(self):
        g = Guardian("open")
        self.assertEqual(g.classify_command("rm -rf /").decision, Decision.BLOCK)
        self.assertEqual(g.classify_command("git push --force origin main").decision, Decision.BLOCK)

    def test_routine_commands_allowed_guarded(self):
        g = Guardian("guarded")
        self.assertEqual(g.classify_command("npm test").decision, Decision.ALLOW)
        self.assertEqual(g.classify_command("python -m unittest").decision, Decision.ALLOW)

    def test_locked_requires_gate_for_production(self):
        g = Guardian("locked")
        self.assertEqual(g.classify_command("kubectl apply -f prod.yaml").decision, Decision.REQUIRE_APPROVAL)
        self.assertFalse(g.can_write(".env"))
        self.assertFalse(g.can_write(".git/config"))

class RoleIsolationTests(unittest.TestCase):
    def test_review_roles_can_write_run_artifacts_but_not_product(self):
        g=Guardian("guarded")
        self.assertTrue(g.can_write(".aah/runs/RUN-1/FINDINGS.json",role="aah-evaluator"))
        self.assertFalse(g.can_write("src/app.py",role="aah-evaluator"))
        self.assertTrue(g.can_write("src/app.py",role="aah-builder"))

    def test_review_role_bash_source_mutation_is_blocked(self):
        g=Guardian("guarded")
        self.assertEqual(g.classify_command("sed -i 's/x/y/' src/app.py",role="aah-evaluator").decision,Decision.BLOCK)
        self.assertEqual(g.classify_command("pytest -q",role="aah-evaluator").decision,Decision.ALLOW)
        self.assertEqual(g.classify_command("cat result > .aah/runs/RUN-1/logs/test.txt",role="aah-evaluator").decision,Decision.BLOCK)

class ReviewShellAllowlistTests(unittest.TestCase):
    def test_review_role_cannot_bypass_read_guard_with_cat_env(self):
        g=Guardian("guarded")
        self.assertEqual(g.classify_command("cat .env",role="aah-evaluator").decision,Decision.BLOCK)

    def test_review_role_can_run_bounded_tests_but_not_arbitrary_python(self):
        g=Guardian("guarded")
        self.assertEqual(g.classify_command("python -m pytest tests/test_x.py -q",role="aah-tester").decision,Decision.ALLOW)
        self.assertEqual(g.classify_command("python -c 'open(\"src/x.py\",\"w\").write(\"x\")'",role="aah-evaluator").decision,Decision.BLOCK)

    def test_review_role_cannot_chain_safe_command_into_mutation(self):
        g=Guardian("guarded")
        self.assertEqual(g.classify_command("pytest && rm -rf src",role="aah-tester").decision,Decision.BLOCK)

if __name__ == "__main__": unittest.main()
