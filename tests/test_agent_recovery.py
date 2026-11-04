import importlib.util
from unittest import TestCase, skipUnless

from incident_lab.agent import investigate_agent
from incident_lab.providers import ModelReply
from incident_lab.replay import load_incidents


def tools():
    return [
        {"type": "tool_use", "id": tool, "name": tool, "input": {"service": "orders-api"}}
        for tool in ("get_logs", "get_metrics", "get_deployments")
    ]


def submit(id, cause=None, status="abstained"):
    return [
        {
            "type": "tool_use",
            "id": id,
            "name": "submit_investigation",
            "input": {
                "status": status,
                "suspected_cause": cause,
                "explanation": "Evidence is incomplete or ambiguous.",
                "next_step": "Collect discriminating telemetry.",
                "evidence_ids": [],
                "runbook_ids": [],
            },
        }
    ]


class Sequence:
    name = "test-double"
    model = "no-inference"
    live = False

    def __init__(self, messages):
        self.messages = iter(messages)
        self.calls = 0
        self.requests = []

    def complete(self, **kwargs):
        self.calls += 1
        self.requests.append(kwargs)
        return ModelReply(next(self.messages))


@skipUnless(importlib.util.find_spec("langgraph") is not None, "Install agent dependencies")
class AgentRecoveryTests(TestCase):
    def test_text_only_reply_can_recover_to_a_real_submission(self):
        provider = Sequence(
            [
                tools(),
                [{"type": "text", "text": "I cannot conclude from these observations."}],
                submit("final"),
            ]
        )
        result = investigate_agent(load_incidents()["INC-004"], provider)
        self.assertEqual("abstained", result["status"])
        self.assertEqual(1, result["repairs_used"])
        self.assertEqual(3, result["measurement"]["model_turns"])
        self.assertIn("protocol_repair", [event["status"] for event in result["model_trace"]])

    def test_repeated_text_does_not_become_a_silent_success(self):
        provider = Sequence(
            [
                tools(),
                [{"type": "text", "text": "Unknown"}],
                [{"type": "text", "text": "Still unknown"}],
            ]
        )
        result = investigate_agent(load_incidents()["INC-004"], provider, max_repairs=1)
        self.assertEqual("failed", result["status"])
        self.assertEqual(3, provider.calls)

    def test_invalid_submission_and_tool_outage_can_recover_to_abstention(self):
        bad = submit("bad", "invalid_configuration", "hypothesis")
        bad[0]["input"]["evidence_ids"] = ["log-config"]
        provider = Sequence(
            [
                tools(),
                bad,
                [{"type": "text", "text": "Deployment telemetry is unavailable."}],
                submit("final"),
            ]
        )
        result = investigate_agent(load_incidents()["INC-006"], provider)
        self.assertEqual("abstained", result["status"])
        self.assertEqual(2, result["repairs_used"])
        self.assertTrue(result["tool_errors"])

    def test_invalid_submissions_stop_at_the_repair_budget(self):
        provider = Sequence(
            [
                tools(),
                submit("bad-1", "invalid_configuration", "abstained"),
                submit("bad-2", "invalid_configuration", "abstained"),
            ]
        )
        result = investigate_agent(load_incidents()["INC-004"], provider, max_repairs=1)
        self.assertEqual("failed", result["status"])
        self.assertEqual("repair_budget_exhausted", result["stop_reason"])

    def test_gateway_cannot_be_bound_to_another_incident(self):
        from incident_lab.tools import ToolGateway

        with self.assertRaisesRegex(ValueError, "must match"):
            investigate_agent(
                load_incidents()["INC-004"],
                Sequence([]),
                gateway=ToolGateway(load_incidents()["INC-001"]),
            )

    def test_insufficient_snapshot_exposes_only_an_abstention_submission(self):
        provider = Sequence([tools(), submit("final")])
        result = investigate_agent(load_incidents()["INC-004"], provider)
        definitions = provider.requests[-1]["tools"]
        self.assertEqual(["submit_investigation"], [tool["name"] for tool in definitions])
        self.assertEqual(
            ["abstained"], definitions[0]["input_schema"]["properties"]["status"]["enum"]
        )
        self.assertTrue(result["model_trace"][-1]["required_abstention"])
