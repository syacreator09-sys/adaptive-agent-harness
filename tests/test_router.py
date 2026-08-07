import unittest
from factory.router import AdaptiveRouter

class RouterTests(unittest.TestCase):
    def test_profile_and_guardian_are_separate_axes(self):
        r = AdaptiveRouter({"claude":{"available":True}, "codex":{"available":True}})
        d = r.route("change production authentication token handling", complexity_hint=20, risk_hint=90)
        self.assertEqual(d["profile"], "lite")
        self.assertEqual(d["guardian"], "locked")

    def test_cross_provider_evaluation_preferred(self):
        r = AdaptiveRouter({"claude":{"available":True}, "codex":{"available":True}})
        assignments = r.assign_roles(["planner","builder","evaluator"], policy="quality")
        self.assertNotEqual(assignments["builder"]["provider"], assignments["evaluator"]["provider"])

if __name__ == "__main__": unittest.main()

class AutoBehaviorTests(unittest.TestCase):
    def test_domain_roles_are_resolved(self):
        from factory.cli import _roles_for
        self.assertIn("content_producer", _roles_for("lite","content"))
        self.assertIn("fact_checker", _roles_for("pro","research"))

class AuthAwareRoutingTests(unittest.TestCase):
    def test_explicitly_logged_out_provider_is_not_schedulable(self):
        r=AdaptiveRouter({"claude":{"available":True,"authenticated":False},"codex":{"available":True,"authenticated":None}})
        self.assertEqual(r.available(),["codex"])
