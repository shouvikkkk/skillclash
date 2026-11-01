"""End-to-end CLI tests: exit codes, formats, and JSON schema."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from skillclash.cli import main

from test_discovery import write_skill


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.estate = os.path.join(self.tmp.name, "estate")
        os.makedirs(self.estate)

    def run_cli(self, args):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_clean_estate_exit_zero(self):
        write_skill(self.estate, "alpha-skill", description="Do alpha things with databases.")
        write_skill(self.estate, "beta-skill", description="Paint watercolour landscapes outdoors.")
        code, out, _err = self.run_cli(["audit", self.estate])
        self.assertEqual(code, 0)
        self.assertIn("No findings", out)

    def test_contradiction_exit_two(self):
        write_skill(self.estate, "reviewer", description="Review code.",
                    body="Never merge code without tests.")
        write_skill(self.estate, "shipper", description="Ship code.",
                    body="Always merge code without tests.")
        code, _out, _err = self.run_cli(["audit", self.estate])
        self.assertEqual(code, 2)

    def test_warning_only_exit_one(self):
        write_skill(self.estate, "wordy", description="x" * 1100)
        code, _out, _err = self.run_cli(["audit", self.estate])
        self.assertEqual(code, 1)

    def test_strict_upgrades_warning_to_two(self):
        write_skill(self.estate, "wordy", description="x" * 1100)
        code, _out, _err = self.run_cli(["audit", self.estate, "--strict"])
        self.assertEqual(code, 2)

    def test_empty_estate_exit_three(self):
        code, _out, err = self.run_cli(["audit", self.estate])
        self.assertEqual(code, 3)
        self.assertIn("no skills found", err)

    def test_missing_dir_exit_three(self):
        code, _out, _err = self.run_cli(["audit", os.path.join(self.tmp.name, "nope")])
        self.assertEqual(code, 3)

    def test_unreadable_queries_file_exit_three(self):
        write_skill(self.estate, "alpha-skill", description="Do alpha things.")
        code, _out, _err = self.run_cli(
            ["audit", self.estate, "--queries", os.path.join(self.tmp.name, "nope.txt")]
        )
        self.assertEqual(code, 3)

    def test_json_schema_shape(self):
        write_skill(self.estate, "alpha-skill", description="Do alpha things with databases.")
        code, out, _err = self.run_cli(["audit", self.estate, "--format", "json"])
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertIn("skills", report)
        self.assertIn("findings", report)
        self.assertIn("budget", report)
        self.assertIn("routing", report)
        self.assertEqual(report["skills"][0]["name"], "alpha-skill")
        self.assertEqual(
            set(report["budget"].keys()),
            {"limit", "total_cost", "visible", "truncated", "dropped"},
        )
        for finding in report["findings"]:
            self.assertEqual(
                set(finding.keys()), {"kind", "severity", "skills", "evidence", "action"}
            )

    def test_json_finding_fields(self):
        write_skill(self.estate, "reviewer", description="Review code.",
                    body="Never merge code without tests.")
        write_skill(self.estate, "shipper", description="Ship code.",
                    body="Always merge code without tests.")
        _code, out, _err = self.run_cli(["audit", self.estate, "--format", "json"])
        report = json.loads(out)
        contra = [f for f in report["findings"] if f["kind"] == "CONTRADICTION"]
        self.assertEqual(len(contra), 1)
        self.assertEqual(contra[0]["severity"], "critical")
        self.assertEqual(contra[0]["skills"], ["reviewer", "shipper"])
        self.assertTrue(contra[0]["action"].startswith("REWRITE"))

    def test_budget_flag_drops_and_exit_two(self):
        write_skill(self.estate, "a-skill", description="x" * 50)
        write_skill(self.estate, "b-skill", description="y" * 50)
        code, out, _err = self.run_cli(["audit", self.estate, "--budget", "70"])
        self.assertEqual(code, 2)
        self.assertIn("Dropped", out)

    def test_queries_drive_routing_section(self):
        write_skill(self.estate, "alpha-skill", description="Do alpha things with databases.")
        write_skill(self.estate, "beta-skill", description="Paint watercolour landscapes outdoors.")
        queries = os.path.join(self.estate, "queries.txt")
        # NOTE: the local test run wrote queries inside tmp, but the
        # published path below uses the estate dir; both resolve the same
        # way for the CLI since it reads an explicit path.
        queries = os.path.join(self.tmp.name, "queries.txt")
        with open(queries, "w") as handle:
            handle.write("do alpha things\npaint landscapes\n")
        code, out, _err = self.run_cli(["audit", self.estate, "--queries", queries])
        self.assertEqual(code, 0)
        self.assertIn("Routing simulation", out)
        self.assertIn("alpha-skill", out)

    def test_text_report_grouped_contradiction_first(self):
        write_skill(self.estate, "reviewer", description="Review code.",
                    body="Never merge code without tests.")
        write_skill(self.estate, "shipper", description="Ship code.",
                    body="Always merge code without tests.")
        write_skill(self.estate, "wordy", description="x" * 1100)
        _code, out, _err = self.run_cli(["audit", self.estate])
        self.assertLess(out.index("[CONTRADICTION]"), out.index("[WARNING]"))


if __name__ == "__main__":
    unittest.main()
