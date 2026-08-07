import json
import tempfile
import unittest
from pathlib import Path

from factory.artifacts import ArtifactStore
from factory.config import AAHConfig
from factory.models import Phase, Profile, GuardianMode
from factory.state import RunStateStore


class CoreTests(unittest.TestCase):
    def test_artifacts_and_state_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = ArtifactStore(root)
            run = store.create_run("hello", profile=Profile.LITE.value, guardian=GuardianMode.OPEN.value, domain="code")
            self.assertTrue(run.run_dir.exists())
            payload = json.loads((run.run_dir / "REQUEST.json").read_text())
            self.assertEqual(payload["request"], "hello")
            state = RunStateStore(run.run_dir)
            state.transition(Phase.PLANNING)
            self.assertEqual(state.load()["phase"], Phase.PLANNING.value)
            store.append_jsonl(run.run_dir, "EVIDENCE.jsonl", {"id":"E-001", "kind":"test", "ok":True})
            lines = (run.run_dir / "EVIDENCE.jsonl").read_text().strip().splitlines()
            self.assertEqual(len(lines), 1)

    def test_config_defaults_and_local_save(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)
            cfg = AAHConfig.load(target)
            self.assertEqual(cfg.data["billing"]["mode"], "subscription_only")
            self.assertEqual(cfg.data["execution"]["profile"], "auto")
            cfg.data["execution"]["profile"] = "pro"
            cfg.save(target)
            loaded = AAHConfig.load(target)
            self.assertEqual(loaded.data["execution"]["profile"], "pro")

if __name__ == "__main__":
    unittest.main()
