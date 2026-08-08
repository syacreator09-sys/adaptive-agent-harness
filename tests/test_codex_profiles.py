import tempfile
import tomllib
import unittest
from pathlib import Path
from factory.codex_profiles import install_profiles, has_profiles, START


class CodexProfileTests(unittest.TestCase):
    def test_profiles_merge_parse_and_do_not_change_user_default(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); path = root / ".codex" / "config.toml"; path.parent.mkdir(parents=True)
            path.write_text('model = "custom"\ndefault_permissions = "my_profile"\n')
            result = install_profiles(root)
            self.assertTrue(result["installed"])
            text = path.read_text()
            parsed = tomllib.loads(text)
            self.assertEqual(parsed["default_permissions"], "my_profile")
            self.assertIn("aah_readonly", parsed["permissions"])
            self.assertIn("aah_workspace", parsed["permissions"])
            self.assertIn(":workspace_roots", parsed["permissions"]["aah_readonly"]["filesystem"])
            self.assertIn('".env" = "deny"', text)
            self.assertTrue(has_profiles(root))
            install_profiles(root)
            self.assertEqual(path.read_text().count(START), 1)

    def test_malformed_config_is_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); path = root / ".codex" / "config.toml"; path.parent.mkdir(parents=True)
            bad = "not = [valid"
            path.write_text(bad)
            result = install_profiles(root)
            self.assertFalse(result["installed"])
            self.assertEqual(path.read_text(), bad)


if __name__ == "__main__":
    unittest.main()
