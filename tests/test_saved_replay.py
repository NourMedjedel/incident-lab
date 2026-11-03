import copy
import io
import json
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from incident_lab.cli import main
from incident_lab.evaluation import replay_comparison

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/ollama-qwen3-8b/comparison.json"


class SavedReplayTests(TestCase):
    def setUp(self):
        self.saved = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def replay_modified(self, modify):
        value = copy.deepcopy(self.saved)
        modify(value)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "comparison.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            return replay_comparison(path)

    def test_saved_scores_reproduce_without_model_access(self):
        with (
            patch("incident_lab.chat_providers.ChatProvider.post") as post,
            patch("incident_lab.providers.AnthropicProvider.complete") as complete,
        ):
            result = replay_comparison(EXAMPLE)
        self.assertEqual(7, result["baseline"]["summary"]["behavior_correct_count"])
        self.assertEqual(5, result["agent"]["summary"]["behavior_correct_count"])
        self.assertEqual(1, result["agent"]["summary"]["failed_count"])
        self.assertEqual(0, result["replay"]["new_model_requests"])
        post.assert_not_called()
        complete.assert_not_called()

    def test_fixture_changes_are_not_silently_regraded(self):
        with self.assertRaisesRegex(ValueError, "Fixture hashes"):
            self.replay_modified(lambda value: value["provenance"].update(fixture_sha256={}))

    def test_missing_case_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "every fixture"):
            self.replay_modified(lambda value: value["agent_traces"].pop("INC-008"))

    def test_mismatched_model_metadata_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "metadata"):
            self.replay_modified(
                lambda value: value["agent_traces"]["INC-001"].update(model="other")
            )

    def test_scripted_results_cannot_be_presented_as_real_model_results(self):
        with self.assertRaisesRegex(ValueError, "real-model"):
            self.replay_modified(lambda value: value.update(provider="scripted-demo"))

    def test_missing_trace_fields_are_an_actionable_error(self):
        with self.assertRaisesRegex(ValueError, "structure"):
            self.replay_modified(lambda value: value["agent_traces"]["INC-001"].pop("measurement"))

    def test_missing_file_is_an_actionable_error(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(ValueError, "Cannot read"),
        ):
            replay_comparison(Path(directory) / "missing.json")

    def test_cli_reports_preserved_failures_without_failing_offline_reproduction(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()) as output:
            result = Path(directory) / "result.json"
            report = Path(directory) / "report.md"
            self.assertEqual(
                0, main(["replay", str(EXAMPLE), "--output", str(result), "--report", str(report)])
            )
            self.assertEqual(1, json.loads(result.read_text())["agent"]["summary"]["failed_count"])
            self.assertIn("zero model requests", report.read_text())
        self.assertIn("Offline replay", output.getvalue())
