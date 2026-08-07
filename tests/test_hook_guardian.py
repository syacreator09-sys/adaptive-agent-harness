import io, json, os, tempfile, unittest
from contextlib import redirect_stdout
from unittest import mock
from factory.hook_guardian import main
from factory.guardian import Guardian, Decision

class HookGuardianTests(unittest.TestCase):
    def call(self,payload,mode="guarded"):
        out=io.StringIO()
        with mock.patch("sys.stdin",io.StringIO(json.dumps(payload))), mock.patch.dict(os.environ,{"AAH_GUARDIAN_MODE":mode},clear=False), redirect_stdout(out):
            rc=main()
        return rc, json.loads(out.getvalue()) if out.getvalue().strip() else None

    def test_blocks_sensitive_env_read(self):
        rc,data=self.call({"tool_name":"Read","tool_input":{"file_path":"/tmp/project/.env"},"cwd":"/tmp/project"})
        self.assertEqual(rc,0); self.assertEqual(data["hookSpecificOutput"]["permissionDecision"],"deny")

    def test_allows_run_artifact_write_but_blocks_runtime(self):
        g=Guardian("guarded")
        self.assertTrue(g.can_write(".aah/runs/RUN-1/SPEC.md"))
        self.assertFalse(g.can_write(".aah/runtime/factory/guardian.py"))

    def test_locked_escalates_production_command(self):
        rc,data=self.call({"tool_name":"Bash","tool_input":{"command":"kubectl apply -f prod.yaml"},"cwd":"/tmp/project"},"locked")
        self.assertEqual(data["hookSpecificOutput"]["permissionDecision"],"ask")

class NativeAgentRoleHookTests(unittest.TestCase):
    def call_role(self,payload,mode="guarded"):
        out=io.StringIO()
        with mock.patch("sys.stdin",io.StringIO(json.dumps(payload))), mock.patch.dict(os.environ,{"AAH_GUARDIAN_MODE":mode},clear=False), redirect_stdout(out):
            rc=main()
        return rc, json.loads(out.getvalue()) if out.getvalue().strip() else None

    def test_agent_type_enforces_artifact_only_write(self):
        rc,data=self.call_role({"agent_type":"aah-evaluator","tool_name":"Write","tool_input":{"file_path":"/tmp/project/src/app.py"},"cwd":"/tmp/project"})
        self.assertEqual(rc,0); self.assertEqual(data["hookSpecificOutput"]["permissionDecision"],"deny")
        rc2,data2=self.call_role({"agent_type":"aah-evaluator","tool_name":"Write","tool_input":{"file_path":"/tmp/project/.aah/runs/RUN-1/FINDINGS.json"},"cwd":"/tmp/project"})
        self.assertEqual(rc2,0); self.assertIsNone(data2)

class DynamicGuardianModeTests(unittest.TestCase):
    def test_native_hook_reads_latest_run_guardian_mode(self):
        import pathlib
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td); run=root/'.aah'/'runs'/'RUN-1'; run.mkdir(parents=True)
            (run/'STATE.json').write_text(json.dumps({'guardian':'locked'}))
            payload={'tool_name':'Bash','tool_input':{'command':'kubectl apply -f prod.yaml'},'cwd':str(root)}
            out=io.StringIO()
            with mock.patch('sys.stdin',io.StringIO(json.dumps(payload))), mock.patch.dict(os.environ,{'AAH_TARGET_ROOT':str(root)},clear=True), redirect_stdout(out):
                rc=main()
            data=json.loads(out.getvalue())
            self.assertEqual(rc,0)
            self.assertEqual(data['hookSpecificOutput']['permissionDecision'],'ask')

if __name__=="__main__": unittest.main()
