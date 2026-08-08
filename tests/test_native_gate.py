import tempfile
import unittest
from pathlib import Path

from factory.artifacts import ArtifactStore
from factory.cli import _native_mandatory_gates
from factory.evidence import EvidenceStore


class NativeGateTests(unittest.TestCase):
    def test_pro_requires_positive_technical_test_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td); store=ArtifactStore(target); run=store.create_run("x","pro","guarded","code")
            gates=_native_mandatory_gates(run)
            self.assertEqual(gates,[{"name":"technical_tests","ok":False}])
            EvidenceStore(run.run_dir).append({"id":"T1","type":"technical_test","ok":True})
            self.assertEqual(_native_mandatory_gates(run),[{"name":"technical_tests","ok":True}])

    def test_factory_requires_each_task_system_and_security(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td); store=ArtifactStore(target); run=store.create_run("x","factory","guarded","code")
            store.write_json(run.run_dir,"TASKS.json",{"tasks":[
                {"id":"A","profile":"lite","depends_on":[],"acceptance":["A passes"]},
                {"id":"B","profile":"pro","depends_on":["A"],"acceptance":["B passes"]},
            ]})
            ev=EvidenceStore(run.run_dir)
            ev.append({"id":"A1","type":"task_verification","task_id":"A","ok":True})
            ev.append({"id":"SYS","type":"system_test","ok":True})
            ev.append({"id":"SEC","type":"security","ok":True})
            gates={g["name"]:g["ok"] for g in _native_mandatory_gates(run)}
            self.assertFalse(gates["task_graph"])
            ev.append({"id":"B1","type":"task_verification","task_id":"B","ok":True})
            gates={g["name"]:g["ok"] for g in _native_mandatory_gates(run)}
            self.assertTrue(gates["task_graph"])
            self.assertTrue(gates["system_test"])
            self.assertTrue(gates["security"])

    def test_research_factory_does_not_require_code_security_gate(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td); store=ArtifactStore(target); run=store.create_run("x","factory","guarded","research")
            store.write_json(run.run_dir,"TASKS.json",{"tasks":[{"id":"R","profile":"lite","depends_on":[],"acceptance":["claim verified"]}]})
            ev=EvidenceStore(run.run_dir)
            ev.append({"id":"R1","type":"task_verification","task_id":"R","ok":True})
            ev.append({"id":"SYS","type":"system_test","ok":True})
            names=[g["name"] for g in _native_mandatory_gates(run)]
            self.assertNotIn("security",names)


if __name__=="__main__":
    unittest.main()
