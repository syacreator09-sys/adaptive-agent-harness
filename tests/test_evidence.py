import tempfile
import unittest
from pathlib import Path

from factory.evidence import EvidenceStore, redact


class EvidenceStoreAppendTests(unittest.TestCase):
    def test_record_with_id_is_kept_as_is(self):
        with tempfile.TemporaryDirectory() as d:
            ev = EvidenceStore(Path(d))
            ev.append({"id": "E-1", "kind": "test", "detail": "ok"})
            self.assertEqual(ev.ids(), {"E-1"})

    def test_record_without_id_gets_a_stable_derived_id_instead_of_crashing(self):
        """Real bug found live (plan AUTONOMÍA TOTAL, 2026-08-07): a fresh
        builder agent returned evidence with no "id" field and the whole
        LITE run crashed with ValueError, stuck mid-phase, no FINAL_REPORT
        ever written. Must degrade gracefully instead."""
        with tempfile.TemporaryDirectory() as d:
            ev = EvidenceStore(Path(d))
            ev.append({"kind": "test", "detail": "unittest passed"})
            ids = ev.ids()
            self.assertEqual(len(ids), 1)
            self.assertTrue(next(iter(ids)).startswith("E-auto-"))

    def test_auto_id_is_deterministic_for_identical_content(self):
        with tempfile.TemporaryDirectory() as d:
            ev = EvidenceStore(Path(d))
            ev.append({"kind": "test", "detail": "same content"})
            ev.append({"kind": "test", "detail": "same content"})
            rows = ev.all()
            self.assertEqual(rows[0]["id"], rows[1]["id"])

    def test_different_content_gets_different_auto_ids(self):
        with tempfile.TemporaryDirectory() as d:
            ev = EvidenceStore(Path(d))
            ev.append({"kind": "test", "detail": "first"})
            ev.append({"kind": "test", "detail": "second"})
            rows = ev.all()
            self.assertNotEqual(rows[0]["id"], rows[1]["id"])

    def test_auto_id_record_content_is_not_fabricated_or_altered(self):
        with tempfile.TemporaryDirectory() as d:
            ev = EvidenceStore(Path(d))
            ev.append({"kind": "test", "detail": "unchanged content"})
            row = ev.all()[0]
            self.assertEqual(row["kind"], "test")
            self.assertEqual(row["detail"], "unchanged content")

    def test_secret_looking_values_still_redacted_on_auto_id_path(self):
        with tempfile.TemporaryDirectory() as d:
            ev = EvidenceStore(Path(d))
            ev.append({"kind": "test", "detail": "api_key=sk-abcdefghijklmnop"})
            row = ev.all()[0]
            self.assertNotIn("sk-abcdefghijklmnop", row["detail"])

    def test_bare_string_record_does_not_crash(self):
        """Real bug found live at PRO scale (plan AUTONOMÍA TOTAL A6,
        2026-08-08, first-ever real PRO run, RUN-20260808-001): a PRO
        evaluator's "evidence" list contained a bare string, not an
        object -- record.get("id") crashed with AttributeError before
        ever reaching the missing-id fallback, killing the whole run
        with no FINAL_REPORT. A bare string is real content worth
        keeping, not discarding."""
        with tempfile.TemporaryDirectory() as d:
            ev = EvidenceStore(Path(d))
            ev.append("confirmed no hardcoded secrets in config.py")
            row = ev.all()[0]
            self.assertEqual(row["detail"], "confirmed no hardcoded secrets in config.py")
            self.assertTrue(row["id"].startswith("E-auto-"))


class RedactTests(unittest.TestCase):
    def test_redacts_key_value_pattern(self):
        self.assertIn("[REDACTED]", redact("token=abc123def456"))

    def test_redacts_sk_prefixed_secret(self):
        self.assertEqual(redact("key sk-abcdefghijklmnop here"), "key [REDACTED] here")


if __name__ == "__main__":
    unittest.main()
