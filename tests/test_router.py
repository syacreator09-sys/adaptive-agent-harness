import unittest
from factory.router import AdaptiveRouter
from factory.cli import _roles_for


class RouterTests(unittest.TestCase):
    def test_profile_and_guardian_are_independent_axes(self):
        router = AdaptiveRouter({"claude": {"available": True}, "codex": {"available": True}})
        decision = router.route("change production authentication token handling", complexity_hint=20, risk_hint=90)
        self.assertEqual(decision["profile"], "lite")
        self.assertEqual(decision["guardian"], "locked")

    def test_complexity_thresholds_select_lite_pro_factory(self):
        router = AdaptiveRouter({})
        self.assertEqual(router.route("x", complexity_hint=25)["profile"], "lite")
        self.assertEqual(router.route("x", complexity_hint=26)["profile"], "pro")
        self.assertEqual(router.route("x", complexity_hint=71)["profile"], "factory")

    def test_cross_provider_evaluation_is_preferred(self):
        router = AdaptiveRouter({
            "claude": {"available": True, "authenticated": True},
            "codex": {"available": True, "authenticated": True},
        })
        assignments = router.assign_roles(["planner", "builder", "evaluator"], policy="quality")
        self.assertNotEqual(assignments["builder"]["provider"], assignments["evaluator"]["provider"])
        self.assertEqual(assignments["planner"]["provider"], "claude")
        self.assertEqual(assignments["builder"]["provider"], "codex")

    def test_claude_only_lite_preserves_opus_producer_sonnet_evaluator_recommendations(self):
        router = AdaptiveRouter({"claude": {"available": True, "authenticated": True}})
        assignments = router.assign_roles(["planner", "builder", "evaluator"], policy="balanced")
        self.assertEqual(assignments["planner"]["model"], "opus")
        self.assertEqual(assignments["builder"]["model"], "opus")
        self.assertEqual(assignments["evaluator"]["model"], "sonnet")

    def test_model_only_override_does_not_erase_provider_or_capability(self):
        router = AdaptiveRouter({"claude": {"available": True, "authenticated": True}})
        assignment = router.assign_roles(
            ["planner"], policy="balanced", overrides={"planner": {"model": "custom-model"}}
        )["planner"]
        self.assertEqual(assignment["provider"], "claude")
        self.assertEqual(assignment["model"], "custom-model")
        self.assertEqual(assignment["capability"], "deep_reasoning")

    def test_explicitly_logged_out_provider_is_not_schedulable(self):
        router = AdaptiveRouter({
            "claude": {"available": True, "authenticated": False},
            "codex": {"available": True, "authenticated": None},
        })
        self.assertEqual(router.available(), ["codex"])

    def test_domain_roles_are_resolved(self):
        self.assertIn("content_producer", _roles_for("lite", "content"))
        self.assertIn("fact_checker", _roles_for("pro", "research"))


if __name__ == "__main__":
    unittest.main()
