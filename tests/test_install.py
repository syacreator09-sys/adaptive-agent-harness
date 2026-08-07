import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class InstallerTests(unittest.TestCase):
    def test_existing_project_is_preserved_and_no_actions_are_created(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)
            (target/'package.json').write_text('{"scripts":{"test":"echo ok"}}')
            (target/'.env').write_text('SECRET_TOKEN=super-secret\nPUBLIC_URL=https://example.test\n')
            (target/'AGENTS.md').write_text('# Existing rules\nKeep me.\n')
            settings=target/'.claude'/'settings.local.json'; settings.parent.mkdir(parents=True)
            settings.write_text(json.dumps({'hooks':{'PreToolUse':[{'matcher':'Bash','hooks':[{'type':'command','command':'echo existing'}]}]}}))
            codex=target/'.codex'/'config.toml'; codex.parent.mkdir(parents=True); codex.write_text('model = "custom"\n')
            env=os.environ.copy(); env['AAH_NO_GIT_INIT']='1'
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

if __name__=='__main__': unittest.main()
