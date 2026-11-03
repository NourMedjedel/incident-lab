import copy
import importlib.util
import io
import json
import os
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import TestCase, skipUnless
from unittest.mock import Mock, patch

from incident_lab.agent import investigate_agent
from incident_lab.cli import main
from incident_lab.evaluation import compare, evaluate
from incident_lab.providers import (
    AnthropicProvider,
    ModelReply,
    ProviderError,
    ScriptedDemoProvider,
)
from incident_lab.replay import load_incidents

HAS_AGENT = importlib.util.find_spec("langgraph") is not None
HAS_ANTHROPIC = importlib.util.find_spec("anthropic") is not None


def call(id, name, **arguments):
    return {"type": "tool_use", "id": id, "name": name, "input": arguments}


def telemetry():
    return [
        call(f"read-{name}", name, service="orders-api")
        for name in ("get_logs", "get_metrics", "get_deployments")
    ]


def submission(**updates):
    value = {
        "status": "hypothesis",
        "suspected_cause": "resource_exhaustion",
        "explanation": "Pool exhaustion is reported in the log and metrics.",
        "next_step": "Inspect connection usage before proposing a change.",
        "evidence_ids": ["log-pool", "metric-pool"],
        "runbook_ids": [],
    }
    value.update(updates)
    return value


class FakeProvider:
    name = "unit-test-double"
    model = "no-real-model"
    live = False

    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []

    def complete(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        return ModelReply(next(self.replies), input_tokens=10, output_tokens=5)


@skipUnless(HAS_AGENT, "Install the optional agent extra to exercise LangGraph")
class AgentTests(TestCase):
    def setUp(self):
        self.incident = load_incidents()["INC-007"]

    def test_scripted_demo_executes_graph_without_inference(self):
        result = investigate_agent(self.incident, ScriptedDemoProvider())
        self.assertEqual("hypothesis", result["status"])
        self.assertEqual("scripted-demo-no-inference", result["mode"])
        self.assertEqual(0, result["measurement"]["llm_calls"])
        self.assertEqual(2, result["measurement"]["model_turns"])
        self.assertIsNone(result["measurement"]["estimated_llm_cost_usd"])

    def test_unseen_citations_are_rejected_then_a_valid_submission_can_recover(self):
        provider = FakeProvider(
            [
                telemetry(),
                [call("bad", "submit_investigation", **submission(evidence_ids=["invented"]))],
                [call("good", "submit_investigation", **submission())],
            ]
        )
        result = investigate_agent(self.incident, provider)
        self.assertEqual("hypothesis", result["status"])
        self.assertTrue(any("not returned" in error for error in result["validation_errors"]))
        self.assertTrue(provider.requests[-1]["messages"][-1]["content"][0]["is_error"])

    def test_submission_must_follow_observations_in_a_separate_turn(self):
        provider = FakeProvider(
            [
                telemetry() + [call("early", "submit_investigation", **submission())],
                [call("later", "submit_investigation", **submission())],
            ]
        )
        result = investigate_agent(self.incident, provider)
        self.assertEqual("hypothesis", result["status"])
        self.assertTrue(any("Submit alone" in error for error in result["validation_errors"]))

    def test_status_of_wrong_json_type_is_validation_feedback_not_a_crash(self):
        provider = FakeProvider(
            [
                telemetry(),
                [call("bad", "submit_investigation", **submission(status=[]))],
                [call("good", "submit_investigation", **submission())],
            ]
        )
        result = investigate_agent(self.incident, provider)
        self.assertEqual("hypothesis", result["status"])
        self.assertIn("Invalid investigation status", result["validation_errors"])

    def test_no_telemetry_prevents_submission(self):
        provider = FakeProvider(
            [[call("unsupported", "submit_investigation", **submission(evidence_ids=[]))]]
        )
        result = investigate_agent(self.incident, provider, max_model_calls=1)
        self.assertEqual("failed", result["status"])
        self.assertNotEqual("abstained", result["status"])

    def test_model_budget_is_a_hard_stop(self):
        provider = FakeProvider(
            [
                [call("one", "get_logs", service="orders-api")],
                [call("two", "get_logs", service="orders-api")],
            ]
        )
        result = investigate_agent(self.incident, provider, max_model_calls=2)
        self.assertEqual("model_budget_exhausted", result["stop_reason"])
        self.assertEqual(2, len(provider.requests))
        self.assertEqual("failed", result["status"])

    def test_tool_budget_blocks_extra_execution(self):
        provider = FakeProvider([telemetry()])
        result = investigate_agent(self.incident, provider, max_model_calls=1, max_tool_calls=1)
        self.assertEqual(1, len(result["trace"]))
        self.assertEqual(2, result["validation_errors"].count("Tool call budget exhausted"))

    def test_unavailable_telemetry_prevents_hypothesis_but_allows_abstention(self):
        provider = FakeProvider(
            [
                telemetry(),
                [
                    call(
                        "bad",
                        "submit_investigation",
                        **submission(
                            suspected_cause="invalid_configuration", evidence_ids=["log-config"]
                        ),
                    )
                ],
                [
                    call(
                        "abstain",
                        "submit_investigation",
                        **submission(
                            status="abstained", suspected_cause=None, evidence_ids=["log-config"]
                        ),
                    )
                ],
            ]
        )
        result = investigate_agent(load_incidents()["INC-006"], provider)
        self.assertEqual("abstained", result["status"])
        self.assertIn(
            "Required telemetry unavailable; submit an abstention", result["validation_errors"]
        )

    def test_write_tool_is_not_available_to_model(self):
        provider = FakeProvider([[call("unsafe", "restart_service", service="orders-api")]])
        result = investigate_agent(self.incident, provider, max_model_calls=1)
        self.assertEqual("error", result["trace"][0]["status"])
        self.assertEqual([], result["trace"][0]["evidence_ids"])

    def test_reserved_python_argument_names_are_rejected_as_tool_data(self):
        provider = FakeProvider([[call("invalid", "get_logs", service="orders-api", self="x")]])
        result = investigate_agent(self.incident, provider, max_model_calls=1)
        self.assertEqual("error", result["trace"][0]["status"])
        self.assertIn("Unexpected tool arguments", result["validation_errors"])

    def test_duplicate_tool_ids_fail_protocol_without_execution(self):
        provider = FakeProvider(
            [
                [
                    call("same", "get_logs", service="orders-api"),
                    call("same", "get_metrics", service="orders-api"),
                ]
            ]
        )
        result = investigate_agent(self.incident, provider)
        self.assertEqual("invalid_tool_protocol", result["stop_reason"])
        self.assertEqual([], result["trace"])

    def test_text_only_reply_is_not_accepted_as_a_diagnosis(self):
        provider = FakeProvider([[{"type": "text", "text": "Definitely a database issue."}]])
        result = investigate_agent(self.incident, provider)
        self.assertEqual("failed", result["status"])
        self.assertIsNone(result["suspected_cause"])
        self.assertEqual("assistant", result["conversation"][-1]["role"])
        self.assertEqual(
            "Definitely a database issue.", result["conversation"][-1]["content"][0]["text"]
        )

    def test_provider_error_is_a_failure_with_unknown_cost(self):
        provider = FakeProvider([])
        provider.live = True  # A test double simulating the accounting of a failed request.
        provider.complete = Mock(side_effect=ProviderError("Provider unavailable"))
        result = investigate_agent(self.incident, provider)
        self.assertEqual("provider_error", result["stop_reason"])
        self.assertEqual("failed", result["status"])
        self.assertFalse(result["measurement"]["usage_complete"])
        self.assertIsNone(result["measurement"]["estimated_llm_cost_usd"])

    def test_rates_are_used_only_for_complete_non_cached_usage(self):
        provider = FakeProvider(
            [telemetry(), [call("final", "submit_investigation", **submission())]]
        )
        provider.live = True  # Accounting-only test; this provider never makes API calls.
        result = investigate_agent(self.incident, provider, input_rate=2, output_rate=4)
        self.assertAlmostEqual(0.00008, result["measurement"]["estimated_llm_cost_usd"])
        self.assertEqual(20, result["measurement"]["input_tokens"])
        self.assertEqual(10, result["measurement"]["output_tokens"])

    def test_only_ticket_metadata_is_sent_before_tool_results(self):
        provider = FakeProvider([[{"type": "text", "text": "No submission"}]])
        investigate_agent(self.incident, provider)
        content = provider.requests[0]["messages"][0]["content"]
        self.assertNotIn("log-pool", content)
        self.assertNotIn("ground_truth", content)
        self.assertNotIn("INC-007", content)

    def test_api_failures_do_not_count_as_correct_abstentions(self):
        provider = FakeProvider([])
        provider.complete = Mock(side_effect=ProviderError("No connection"))
        result = evaluate(lambda case: investigate_agent(case, provider), engine="test-double")
        self.assertEqual(8, result["summary"]["failed_count"])
        self.assertEqual(0, result["summary"]["behavior_correct_count"])

    def test_scripted_provider_is_rejected_for_comparisons(self):
        with self.assertRaisesRegex(ValueError, "cannot be used"):
            compare(ScriptedDemoProvider())

    def test_invalid_budgets_and_unpaired_rates_fail_before_calling_provider(self):
        provider = FakeProvider([])
        for options in (
            {"max_model_calls": 0},
            {"max_tool_calls": True},
            {"input_rate": 1},
            {"input_rate": float("nan"), "output_rate": 2},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                investigate_agent(self.incident, provider, **options)
        self.assertEqual([], provider.requests)

    def test_offline_cli_marks_the_output_as_scripted(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(
                0, main(["agent-demo", "--output", str(Path(directory) / "demo.json")])
            )
        self.assertIn("no inference", output.getvalue())


class ProviderConfigurationTests(TestCase):
    def test_missing_key_is_an_actionable_error(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertRaisesRegex(ProviderError, "Set ANTHROPIC_API_KEY"),
        ):
            AnthropicProvider("example-model")

    def test_missing_model_is_not_silently_guessed(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "unit-test-placeholder"}, clear=True):
            with self.assertRaisesRegex(ProviderError, "Choose an available model"):
                AnthropicProvider()

    def test_live_cli_without_key_does_not_attempt_network(self):
        with patch.dict(os.environ, {}, clear=True), redirect_stderr(io.StringIO()) as error:
            self.assertEqual(2, main(["agent", "--provider", "anthropic"]))
        self.assertIn("ANTHROPIC_API_KEY", error.getvalue())

    @skipUnless(HAS_ANTHROPIC, "Install agent dependencies to check SDK serialization")
    def test_sdk_adapter_preserves_tool_messages_and_disables_hidden_retries(self):
        response = Mock()
        response.content = [Mock()]
        block = call("test-call", "get_logs", service="orders-api")
        response.content[0].model_dump.return_value = block
        response.usage = Mock(
            input_tokens=11,
            output_tokens=7,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )
        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "unit-test-placeholder"}),
            patch("anthropic.Anthropic") as client,
        ):
            client.return_value.messages.create.return_value = response
            provider = AnthropicProvider("test-model")
            reply = provider.complete(
                system="test", messages=[{"role": "user", "content": "test"}], tools=[]
            )
            client.assert_called_once_with(timeout=30.0, max_retries=0)
            self.assertEqual([block], reply.content)
            self.assertEqual(11, reply.input_tokens)
            self.assertEqual(
                "test-model", client.return_value.messages.create.call_args.kwargs["model"]
            )

    @skipUnless(
        HAS_ANTHROPIC, "Install agent dependencies to check the real SDK with a mock transport"
    )
    def test_real_sdk_round_trip_uses_mock_http_transport_without_network(self):
        import anthropic
        import httpx

        requests = []

        def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "id": "msg_unit_test",
                    "type": "message",
                    "role": "assistant",
                    "model": "test-model",
                    "content": [call("tool_test", "get_logs", service="orders-api")],
                    "stop_reason": "tool_use",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 13, "output_tokens": 9},
                },
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
            client = anthropic.Anthropic(
                api_key="unit-test-placeholder", http_client=http_client, max_retries=0
            )
            with (
                patch.dict(os.environ, {"ANTHROPIC_API_KEY": "unit-test-placeholder"}),
                patch("anthropic.Anthropic", return_value=client),
            ):
                reply = AnthropicProvider("test-model").complete(
                    system="test instruction",
                    messages=[{"role": "user", "content": "test incident"}],
                    tools=[],
                )
        self.assertEqual(13, reply.input_tokens)
        self.assertEqual("get_logs", reply.content[0]["name"])
        self.assertEqual("test-model", requests[0]["model"])
        self.assertEqual("test instruction", requests[0]["system"])
