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

if __name__ == "__main__": unittest.main()
