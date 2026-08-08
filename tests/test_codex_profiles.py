import tempfile, unittest
from pathlib import Path
from factory.codex_profiles import install_profiles, has_profiles, START


class CodexProfileTests(unittest.TestCase):
    def test_profiles_merge_without_changing_user_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'.codex'/'config.toml'; p.parent.mkdir(parents=True)
            p.write_text('model = "custom"\ndefault_permissions = "my_profile"\n')
            result=install_profiles(root)
            self.assertTrue(result['installed'])
            text=p.read_text()
            self.assertIn('default_permissions = "my_profile"',text)
            self.assertIn('[permissions.aah_readonly.filesystem]',text)
            self.assertIn('[permissions.aah_readonly.filesystem.":workspace_roots"]',text)
            self.assertNotIn(':project_roots',text)
            self.assertIn('".env" = "deny"',text)
            self.assertTrue(has_profiles(root))
            install_profiles(root)
            self.assertEqual(p.read_text().count(START),1)

    def test_malformed_config_is_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'.codex'/'config.toml'; p.parent.mkdir(parents=True)
            bad='not = [valid'
            p.write_text(bad)
            result=install_profiles(root)
            self.assertFalse(result['installed'])
            self.assertEqual(p.read_text(),bad)


if __name__=='__main__':
    unittest.main()
