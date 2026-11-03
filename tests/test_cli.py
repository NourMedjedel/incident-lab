import io
import json
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import TestCase

from incident_lab.cli import main


class CLITests(TestCase):
    def test_demo_exports_inspectable_trace(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()) as output:
            target = Path(directory) / "trace.json"
            self.assertEqual(0, main(["demo", "--scenario", "INC-001", "--output", str(target)]))
            result = json.loads(target.read_text())
        self.assertIn("synthetic-fixture-replay", output.getvalue())
        self.assertEqual("invalid_configuration", result["suspected_cause"])
        self.assertTrue(result["trace"])

    def test_evaluation_writes_json_and_readable_report(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            target, report = Path(directory) / "result.json", Path(directory) / "report.md"
            self.assertEqual(
                0, main(["evaluate", "--output", str(target), "--report", str(report)])
            )
            self.assertEqual(8, json.loads(target.read_text())["summary"]["case_count"])
            self.assertIn("not independent evidence", report.read_text())

    def test_unknown_scenario_exits_with_an_actionable_error(self):
        with redirect_stderr(io.StringIO()) as output, self.assertRaises(SystemExit) as error:
            main(["demo", "--scenario", "missing"])
        self.assertEqual(2, error.exception.code)
        self.assertIn("use 'list'", output.getvalue())
