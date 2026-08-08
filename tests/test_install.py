import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def fake_codex(bin_dir: Path):
    path=bin_dir/'codex'
    path.write_text('''#!/usr/bin/env sh
if [ "$1" = "--version" ]; then echo "codex 1.0"; exit 0; fi
if [ "$1" = "login" ] && [ "$2" = "status" ]; then echo "logged in"; exit 0; fi
exit 0
''')
    path.chmod(0o755)


class InstallerTests(unittest.TestCase):
    def test_existing_project_is_preserved_and_no_actions_are_created(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/'project'; target.mkdir()
            bin_dir=Path(td)/'bin'; bin_dir.mkdir(); fake_codex(bin_dir)
            (target/'package.json').write_text('{"scripts":{"test":"echo ok"}}')
            (target/'.env').write_text('SECRET_TOKEN=super-secret\nPUBLIC_URL=https://example.test\n')
            (target/'AGENTS.md').write_text('# Existing rules\nKeep me.\n')
            settings=target/'.claude'/'settings.local.json'; settings.parent.mkdir(parents=True)
            settings.write_text(json.dumps({'hooks':{'PreToolUse':[{'matcher':'Bash','hooks':[{'type':'command','command':'echo existing'}]}]}}))
            codex=target/'.codex'/'config.toml'; codex.parent.mkdir(parents=True); codex.write_text('model = "custom"\n')
            env=os.environ.copy(); env['AAH_NO_GIT_INIT']='1'; env['PATH']=str(bin_dir)+os.pathsep+env.get('PATH','')
            cp=subprocess.run(['bash',str(ROOT/'install.sh'),str(target)],env=env,text=True,capture_output=True)
            self.assertEqual(cp.returncode,0,cp.stderr)
            project=json.loads((target/'.aah'/'project.json').read_text())
            self.assertIn('SECRET_TOKEN',project['env_names'])
            self.assertNotIn('super-secret',json.dumps(project))
            self.assertIn('Keep me.',(target/'AGENTS.md').read_text())
            merged=json.loads(settings.read_text())
            entries=merged['hooks']['PreToolUse']
            commands=[h.get('command') for e in entries for h in e.get('hooks',[])]
            self.assertIn('echo existing',commands)
            self.assertIn('.aah/bin/guardian-hook',commands)
            self.assertFalse((target/'.github'/'workflows').exists())
            self.assertTrue((target/'.claude'/'agents'/'aah-task-evaluator.md').exists())
            codex_text=codex.read_text()
            self.assertIn('model = "custom"',codex_text)
            self.assertIn('[permissions.aah_readonly.filesystem]',codex_text)
            self.assertIn(':workspace_roots',codex_text)

    def test_install_creates_new_target_directory(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/'brand-new-project'
            env=os.environ.copy(); env['AAH_NO_GIT_INIT']='1'
            cp=subprocess.run(['bash',str(ROOT/'install.sh'),str(target)],env=env,text=True,capture_output=True)
            self.assertEqual(cp.returncode,0,cp.stderr)
            self.assertTrue(target.is_dir())
            self.assertTrue((target/'.aah'/'bin'/'factory').exists())
            self.assertTrue((target/'.aah'/'project.json').exists())
            self.assertFalse((target/'.github'/'workflows').exists())

    def test_malformed_claude_settings_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td); settings=target/'.claude'/'settings.local.json'; settings.parent.mkdir(parents=True)
            original='{ definitely-not-json '
            settings.write_text(original)
            env=os.environ.copy(); env['AAH_NO_GIT_INIT']='1'
            cp=subprocess.run(['bash',str(ROOT/'install.sh'),str(target)],env=env,text=True,capture_output=True)
            self.assertEqual(cp.returncode,0,cp.stderr)
            self.assertEqual(settings.read_text(),original)
            self.assertIn('preserving unparseable',cp.stderr)


if __name__=='__main__':
    unittest.main()
