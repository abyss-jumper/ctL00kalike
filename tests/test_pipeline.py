import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from ct_lookalike.cli import main
from ct_lookalike.sources import entries_from_crtsh, load_fixture

ROOT = Path(__file__).resolve().parent.parent


class SourceTests(unittest.TestCase):
    def test_multiline_name_value_is_split(self):
        entries = entries_from_crtsh([
            {"name_value": "*.a.test\nb.a.test", "issuer_name": "CA"},
        ])
        self.assertEqual(sorted(e.domain for e in entries), ["a.test", "b.a.test"])

    def test_duplicates_collapse(self):
        entries = entries_from_crtsh([
            {"name_value": "a.test"},
            {"name_value": "A.TEST."},
        ])
        self.assertEqual(len(entries), 1)

    def test_fixture_loads(self):
        entries = load_fixture(ROOT / "data" / "fixtures" / "crtsh_sample.json")
        self.assertIn("acmebank.co", {e.domain for e in entries})


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_demo_json_contract(self):
        code, out, _ = self._run(["--demo", "--no-store", "--format", "json",
                                  "--db", str(Path(self.tmp.name) / "s.db")])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["brand"], "acmebank.com")
        self.assertGreaterEqual(payload["count"], 5)

    def test_controls_are_not_reported(self):
        code, out, _ = self._run(["--demo", "--no-store", "--format", "json",
                                  "--db", str(Path(self.tmp.name) / "s.db")])
        domains = {f["domain"] for f in json.loads(out)["findings"]}
        self.assertNotIn("example.com", domains)
        self.assertNotIn("github.com", domains)

    def test_state_suppresses_second_run(self):
        db = str(Path(self.tmp.name) / "state.db")
        argv = ["--demo", "--format", "json", "--db", db]
        _, first, _ = self._run(argv)
        _, second, _ = self._run(argv)
        self.assertGreater(json.loads(first)["count"], 0)
        self.assertEqual(json.loads(second)["count"], 0)

    def test_fail_on_hit_sets_exit_code(self):
        code, _, _ = self._run(["--demo", "--no-store", "--fail-on-hit",
                                "--db", str(Path(self.tmp.name) / "s.db")])
        self.assertEqual(code, 1)

    def test_missing_brand_is_usage_error(self):
        code, _, err = self._run(["--no-store"])
        self.assertEqual(code, 2)
        self.assertIn("--brand", err)

    def test_out_file_is_written(self):
        target = Path(self.tmp.name) / "report.md"
        code, _, _ = self._run(["--demo", "--no-store", "--out", str(target),
                                "--db", str(Path(self.tmp.name) / "s.db")])
        self.assertEqual(code, 0)
        self.assertIn("# Lookalike domains", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
