import unittest
from factory.agents import AgentRegistry

class AgentTests(unittest.TestCase):
    def test_required_agents_are_prebuilt_and_typed(self):
        reg = AgentRegistry()
        required = {"planner","architect","builder","tester","evaluator","fixer","worker","task_evaluator","integrator","system_tester","security_reviewer","final_reviewer"}
        self.assertTrue(required.issubset(set(reg.names())))
        for name in required:
            agent = reg.get(name)
            for key in ["identity","mission","capability","tools","inputs","outputs","rules"]:
                self.assertIn(key, agent)
        self.assertIn("never modify product code", " ".join(reg.get("evaluator")["rules"]).lower())

if __name__ == "__main__": unittest.main()
