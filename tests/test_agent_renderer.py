import tempfile
import unittest
from pathlib import Path
from factory.agent_renderer import CORE_ROLES, render_all, render_agent


class AgentRendererTests(unittest.TestCase):
    def test_every_core_role_renders_with_fresh_context_and_contract(self):
        for role in CORE_ROLES:
            text = render_agent(role)
            self.assertIn(f"name: aah-{role.replace('_', '-')}", text)
            self.assertIn("Fresh context: **required", text)
            self.assertIn("## Contract", text)
            self.assertIn("Never claim completion", text)

    def test_renderer_check_detects_drift(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            render_all(out)
            self.assertEqual(render_all(out, check=True), [])
            (out / "aah-evaluator.md").write_text("drift\n")
            self.assertIn("aah-evaluator.md", render_all(out, check=True))

    def test_lite_model_recommendations_preserve_producer_verifier_split(self):
        self.assertIn("Recommended Claude class: `opus`", render_agent("planner"))
        self.assertIn("Recommended Claude class: `opus`", render_agent("builder"))
        self.assertIn("Recommended Claude class: `sonnet`", render_agent("evaluator"))


if __name__ == "__main__":
    unittest.main()
