import json
import os
import unittest
import tempfile
from pathlib import Path
from unittest import mock
from factory.providers import ClaudeProvider, CodexProvider, ProviderRegistry, ProviderError
from factory.codex_profiles import install_profiles


class ProviderCommandTests(unittest.TestCase):
    @mock.patch('subprocess.run')
    def test_claude_restricts_and_preapproves_only_role_tools(self, run):
        run.return_value=mock.Mock(returncode=0,stdout=json.dumps({'result':'{}'}),stderr='')
        ClaudeProvider().run('x',Path('.'),model='sonnet',tools=['Read','Bash'],guardian='guarded')
        cmd=run.call_args.args[0]
        self.assertIn('--tools',cmd)
        self.assertEqual(cmd[cmd.index('--tools')+1],'Read,Bash')
        allowed_index=cmd.index('--allowedTools')
        permission_index=cmd.index('--permission-mode')
        self.assertEqual(cmd[allowed_index+1:permission_index],['Read','Bash'])
        self.assertEqual(cmd[permission_index+1],'dontAsk')
        self.assertNotIn('auto',cmd)

    @mock.patch('subprocess.run')
    def test_codex_review_is_read_only(self, run):
        events='\n'.join([
            json.dumps({'type':'item.completed','item':{'id':'1','type':'agent_message','text':'{}'}}),
            json.dumps({'type':'turn.completed','usage':{}}),
        ])+'\n'
        run.return_value=mock.Mock(returncode=0,stdout=events,stderr='')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); install_profiles(root)
            CodexProvider().run('review',root,access='read-only')
        cmd=run.call_args.args[0]
        self.assertIn('--sandbox',cmd)
        self.assertEqual(cmd[cmd.index('--sandbox')+1],'read-only')
        self.assertNotIn('--ask-for-approval',cmd)
        self.assertIn('default_permissions="aah_readonly"',cmd)

    @mock.patch('subprocess.run')
    def test_codex_extracts_nested_agent_message_json(self, run):
        payload={'summary':'ok','artifacts':{'SPEC.md':'x'},'evidence':[]}
        events='\n'.join([
            json.dumps({'type':'thread.started','thread_id':'t'}),
            json.dumps({'type':'turn.started'}),
            json.dumps({'type':'item.completed','item':{'id':'i1','type':'agent_message','text':json.dumps(payload)}}),
            json.dumps({'type':'turn.completed','usage':{'input_tokens':1,'output_tokens':1}}),
        ])+'\n'
        run.return_value=mock.Mock(returncode=0,stdout=events,stderr='')
        with tempfile.TemporaryDirectory() as td:
            result=CodexProvider().run('x',Path(td),access='read-only')
        self.assertEqual(result['summary'],'ok')
        self.assertEqual(result['artifacts']['SPEC.md'],'x')

    @mock.patch('subprocess.run')
    def test_codex_structured_turn_failure_raises_even_exit_zero(self, run):
        events='\n'.join([
            json.dumps({'type':'turn.failed','error':{'message':'quota exceeded'}}),
        ])+'\n'
        run.return_value=mock.Mock(returncode=0,stdout=events,stderr='')
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ProviderError):
                CodexProvider().run('x',Path(td),access='read-only')

    @mock.patch('subprocess.run')
    def test_codex_known_stream_lag_item_does_not_mask_completed_turn(self, run):
        events='\n'.join([
            json.dumps({'type':'item.completed','item':{'id':'err','type':'error','message':'in-process app-server event stream lagged; dropped 12 events'}}),
            json.dumps({'type':'item.completed','item':{'id':'msg','type':'agent_message','text':'{"summary":"done","artifacts":{},"evidence":[]}'}}),
            json.dumps({'type':'turn.completed','usage':{}}),
        ])+'\n'
        run.return_value=mock.Mock(returncode=0,stdout=events,stderr='')
        with tempfile.TemporaryDirectory() as td:
            result=CodexProvider().run('x',Path(td),access='read-only')
        self.assertEqual(result['summary'],'done')
        self.assertTrue(result['provider_warnings'])


class ProviderDiscoveryTests(unittest.TestCase):
    @mock.patch('factory.providers.shutil.which')
    @mock.patch('factory.providers.subprocess.run')
    def test_claude_auth_probe_is_subscription_first(self, run, which):
        which.side_effect=lambda name: f'/usr/bin/{name}' if name=='claude' else None
        def fake_run(cmd, **kwargs):
            if cmd==['claude','--version']:
                return mock.Mock(returncode=0,stdout='Claude 1.0\n',stderr='')
            if cmd==['claude','auth','status']:
                self.assertNotIn('ANTHROPIC_API_KEY',kwargs['env'])
                self.assertNotIn('ANTHROPIC_AUTH_TOKEN',kwargs['env'])
                return mock.Mock(returncode=0,stdout='logged in',stderr='')
            raise AssertionError(cmd)
        run.side_effect=fake_run
        with mock.patch.dict(os.environ,{'ANTHROPIC_API_KEY':'paid','ANTHROPIC_AUTH_TOKEN':'gateway'},clear=False):
            providers=ProviderRegistry.discover()
        self.assertTrue(providers['claude']['available'])
        self.assertTrue(providers['claude']['authenticated'])
        self.assertEqual(providers['claude']['auth'],'subscription_or_cli_managed')

    @mock.patch('factory.providers.shutil.which')
    @mock.patch('factory.providers.subprocess.run')
    def test_codex_unknown_status_command_is_not_false_negative(self, run, which):
        which.side_effect=lambda name: f'/usr/bin/{name}' if name=='codex' else None
        def fake_run(cmd, **kwargs):
            if cmd==['codex','--version']:
                return mock.Mock(returncode=0,stdout='codex 1.0\n',stderr='')
            if cmd==['codex','login','status']:
                return mock.Mock(returncode=2,stdout='',stderr='error: unexpected argument status\nUsage: codex login')
            raise AssertionError(cmd)
        run.side_effect=fake_run
        providers=ProviderRegistry.discover()
        self.assertTrue(providers['codex']['available'])
        self.assertIsNone(providers['codex']['authenticated'])
        self.assertEqual(providers['codex']['auth'],'status_probe_unavailable')


if __name__=='__main__':
    unittest.main()
