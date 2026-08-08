import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory.evidence import EvidenceStore, redact_data, redact_text


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

    def test_bare_string_record_does_not_crash(self):
        """Same failure class found live at PRO scale (plan AUTONOMÍA
        TOTAL A6, 2026-08-08): an evaluator's evidence list containing a
        bare string, not an object, must not crash the run."""
        with tempfile.TemporaryDirectory() as d:
            ev = EvidenceStore(Path(d))
            ev.append("confirmed no hardcoded secrets in config.py")
            row = ev.all()[0]
            self.assertEqual(row["type"], "invalid_evidence_record")
            self.assertFalse(row["ok"])
            self.assertEqual(row["detail"], "confirmed no hardcoded secrets in config.py")

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

    def test_secret_named_field_is_fully_redacted_by_key_name(self):
        """redact_data's real behavior: a field whose KEY matches
        _SECRET_KEY (token/secret/password/etc.) is redacted wholesale by
        name, independent of whether its value matches a content pattern
        -- a stronger guarantee than pattern-matching free text alone."""
        with tempfile.TemporaryDirectory() as d:
            ev = EvidenceStore(Path(d))
            ev.append({"kind": "test", "token": "anything-at-all-not-pattern-shaped"})
            row = ev.all()[0]
            self.assertEqual(row["token"], "[REDACTED]")


class RedactTextTests(unittest.TestCase):
    def test_redacts_sk_prefixed_secret(self):
        self.assertEqual(redact_text("key sk-abcdefghijklmnop here"), "key [REDACTED] here")

    def test_redacts_bearer_token_keeping_prefix(self):
        self.assertEqual(
            redact_text("Authorization: Bearer abcdef123456789012"),
            "Authorization: Bearer [REDACTED]",
        )

    def test_redacts_known_env_secret_value_verbatim(self):
        with patch.dict("os.environ", {"MY_API_KEY": "supersecretvalue123"}, clear=False):
            self.assertEqual(
                redact_text("the value is supersecretvalue123 here"),
                "the value is [REDACTED] here",
            )


class RedactDataTests(unittest.TestCase):
    def test_secret_key_name_redacts_whole_value(self):
        self.assertEqual(redact_data({"password": "anything"}), {"password": "[REDACTED]"})

    def test_session_id_key_is_not_treated_as_secret(self):
        """Audit identifiers like session_id are intentionally kept --
        only credential-shaped session keys (session_token, session_secret)
        are redacted."""
        self.assertEqual(redact_data({"session_id": "abc-123"}), {"session_id": "abc-123"})

    def test_recurses_into_nested_dicts_and_lists(self):
        data = {"outer": {"token": "x"}, "items": [{"secret": "y"}, "plain"]}
        result = redact_data(data)
        self.assertEqual(result["outer"]["token"], "[REDACTED]")
        self.assertEqual(result["items"][0]["secret"], "[REDACTED]")
        self.assertEqual(result["items"][1], "plain")


if __name__ == "__main__":
    unittest.main()
