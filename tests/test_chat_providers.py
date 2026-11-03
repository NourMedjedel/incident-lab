import copy
import importlib.util
import io
import json
import os
from contextlib import redirect_stderr
from unittest import TestCase, skipUnless
from unittest.mock import patch

from incident_lab.chat_providers import GroqProvider, OllamaProvider, chat_messages
from incident_lab.cli import main
from incident_lab.providers import ProviderError

HAS_HTTPX = importlib.util.find_spec("httpx") is not None
HAS_GRAPH = importlib.util.find_spec("langgraph") is not None


class MessageConversionTests(TestCase):
    def setUp(self):
        self.messages = [
            {"role": "user", "content": "Investigate"},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call-1",
                        "name": "get_logs",
                        "input": {"service": "orders-api"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call-1",
                        "is_error": True,
                        "content": "Telemetry unavailable",
                    }
                ],
            },
        ]

    def test_groq_pairs_tool_results_by_id_and_preserves_errors(self):
        original = copy.deepcopy(self.messages)
        result = chat_messages("instruction", self.messages)
        self.assertEqual("call-1", result[-1]["tool_call_id"])
        self.assertTrue(json.loads(result[-1]["content"])["error"])
        self.assertEqual(
            {"service": "orders-api"},
            json.loads(result[-2]["tool_calls"][0]["function"]["arguments"]),
        )
        self.assertEqual(original, self.messages)

    def test_ollama_pairs_results_by_name_and_keeps_arguments_as_objects(self):
        result = chat_messages("instruction", self.messages, ollama=True)
        self.assertEqual("get_logs", result[-1]["tool_name"])
        self.assertIsInstance(result[-2]["tool_calls"][0]["function"]["arguments"], dict)
        self.assertNotIn("id", result[-2]["tool_calls"][0])

    def test_groq_is_the_default_and_missing_key_makes_no_request(self):
        with patch.dict(os.environ, {}, clear=True), redirect_stderr(io.StringIO()) as output:
            self.assertEqual(2, main(["agent"]))
        self.assertIn("GROQ_API_KEY", output.getvalue())

    def test_local_adapter_rejects_cloud_model_tags(self):
        with self.assertRaisesRegex(ProviderError, "local-only"):
            OllamaProvider("example:cloud")


@skipUnless(HAS_HTTPX, "Install the agent extra to exercise HTTP adapters")
class HTTPAdapterTests(TestCase):
    def client(self, handler):
        import httpx

        return httpx.Client(transport=httpx.MockTransport(handler))

    def groq(self, client):
        with (
            patch.dict(os.environ, {"GROQ_API_KEY": "unit-test-placeholder"}),
            patch("httpx.Client", return_value=client),
        ):
            return GroqProvider("test-model")

    def test_groq_tool_response_usage_and_fixed_endpoint(self):
        import httpx

        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "remote-1",
                                        "type": "function",
                                        "function": {
                                            "name": "get_logs",
                                            "arguments": '{"service":"orders-api"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 8},
                },
            )

        with self.client(handler) as client:
            provider = self.groq(client)
            result = provider.complete(system="instructions", messages=[], tools=[])
        self.assertEqual("get_logs", result.content[0]["name"])
        self.assertEqual(12, result.input_tokens)
        self.assertTrue(result.usage_complete)
        self.assertEqual("api.groq.com", requests[0].url.host)
        self.assertEqual("Bearer unit-test-placeholder", requests[0].headers["authorization"])
        self.assertEqual("required", json.loads(requests[0].content)["tool_choice"])

    def test_rate_limit_is_reported_without_retry_or_fallback(self):
        import httpx

        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(429, json={"error": "raw provider detail must not be echoed"})

        with self.client(handler) as client:
            provider = self.groq(client)
            with self.assertRaisesRegex(ProviderError, "rate limit") as error:
                provider.complete(system="test", messages=[], tools=[])
        self.assertEqual(1, len(requests))
        self.assertNotIn("raw provider detail", str(error.exception))

    def test_redirect_is_not_followed(self):
        import httpx

        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(307, headers={"location": "https://other.invalid/paid"})

        with self.client(handler) as client:
            provider = self.groq(client)
            with self.assertRaisesRegex(ProviderError, "307"):
                provider.complete(system="test", messages=[], tools=[])
        self.assertEqual(1, len(requests))

    def test_missing_usage_is_not_complete_zero_token_usage(self):
        import httpx

        with self.client(
            lambda request: httpx.Response(
                200, json={"choices": [{"message": {"content": "test"}}]}
            )
        ) as client:
            result = self.groq(client).complete(system="test", messages=[], tools=[])
        self.assertFalse(result.usage_complete)

    def test_malformed_tool_arguments_are_a_safe_provider_error(self):
        import httpx

        with self.client(
            lambda request: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "id": "id",
                                        "function": {
                                            "name": "get_logs",
                                            "arguments": "broken JSON",
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                },
            )
        ) as client:
            with self.assertRaisesRegex(ProviderError, "invalid tool-calling"):
                self.groq(client).complete(system="test", messages=[], tools=[])

    def test_ollama_uses_loopback_no_auth_and_generates_unique_call_ids(self):
        import httpx

        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "get_logs",
                                    "arguments": {"service": "orders-api"},
                                }
                            }
                        ],
                    },
                    "prompt_eval_count": 15,
                    "eval_count": 7,
                },
            )

        with self.client(handler) as client, patch("httpx.Client", return_value=client):
            provider = OllamaProvider("test-local-model")
            first = provider.complete(system="test", messages=[], tools=[])
            second = provider.complete(system="test", messages=[], tools=[])
        self.assertEqual("127.0.0.1", requests[0].url.host)
        self.assertNotIn("authorization", requests[0].headers)
        self.assertNotEqual(first.content[0]["id"], second.content[0]["id"])
        self.assertEqual(15, first.input_tokens)
        self.assertFalse(json.loads(requests[0].content)["think"])

    @skipUnless(HAS_GRAPH, "Install the agent extra to test the complete mock transport workflow")
    def test_groq_graph_round_trip_keeps_tool_results_and_validates_final_citations(self):
        import httpx

        from incident_lab.agent import investigate_agent
        from incident_lab.replay import load_incidents

        requests = []

        def handler(request):
            payload = json.loads(request.content)
            requests.append(payload)
            if len(requests) == 1:
                calls = [
                    {
                        "id": name,
                        "function": {"name": name, "arguments": '{"service":"orders-api"}'},
                    }
                    for name in ("get_logs", "get_metrics", "get_deployments")
                ]
            else:
                calls = [
                    {
                        "id": "submit",
                        "function": {
                            "name": "submit_investigation",
                            "arguments": json.dumps(
                                {
                                    "status": "hypothesis",
                                    "suspected_cause": "resource_exhaustion",
                                    "explanation": "Pool exhausted.",
                                    "next_step": "Inspect pool usage.",
                                    "evidence_ids": ["log-pool", "metric-pool"],
                                    "runbook_ids": [],
                                }
                            ),
                        },
                    }
                ]
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": None, "tool_calls": calls}}],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 10},
                },
            )

        with self.client(handler) as client:
            result = investigate_agent(load_incidents()["INC-007"], self.groq(client))
        self.assertEqual("hypothesis", result["status"])
        self.assertEqual(2, len(requests))
        self.assertEqual(
            {"get_logs", "get_metrics", "get_deployments"},
            {m["tool_call_id"] for m in requests[1]["messages"] if m["role"] == "tool"},
        )
