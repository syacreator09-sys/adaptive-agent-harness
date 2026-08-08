import unittest
from pathlib import Path

from factory.native_bridge import NATIVE_ROLES, filename_for, render_agent


ROOT=Path(__file__).resolve().parents[1]


class NativeBridgeTests(unittest.TestCase):
    def test_tracked_claude_agents_match_canonical_renderer(self):
        mismatches=[]
        for role in NATIVE_ROLES:
            path=ROOT/'.claude'/'agents'/filename_for(role)
            actual=path.read_text(encoding='utf-8') if path.exists() else None
            expected=render_agent(role)
            if actual!=expected:
                mismatches.append(role)
        self.assertEqual(mismatches,[],f"stale tracked Claude agents: {mismatches}")


if __name__=='__main__':
    unittest.main()
