from dataclasses import replace
from unittest import TestCase

from incident_lab.agent import validate_submission
from incident_lab.policy import assess_evidence
from incident_lab.replay import load_incidents
from incident_lab.tools import ToolError, ToolGateway


def observed(incident):
    gateway = ToolGateway(incident)
    seen = {}
    for tool in ("get_logs", "get_metrics", "get_deployments"):
        try:
            seen.update(
                (record["id"], record) for record in gateway.call(tool, service=incident.service)
            )
        except ToolError:
            pass
    return gateway, seen


def result(cause, ids, status="hypothesis"):
    return {
        "status": status,
        "suspected_cause": cause,
        "explanation": "Review telemetry.",
        "next_step": "Collect discriminating evidence.",
        "evidence_ids": ids,
        "runbook_ids": [],
    }


class EvidencePolicyTests(TestCase):
    def test_generic_http_error_cannot_be_called_a_configuration_failure(self):
        gateway, seen = observed(load_incidents()["INC-004"])
        with self.assertRaisesRegex(ToolError, "INSUFFICIENT_EVIDENCE"):
            validate_submission(result("invalid_configuration", list(seen)), seen, gateway)

    def test_cherry_picking_one_side_of_conflicting_evidence_is_rejected(self):
        gateway, seen = observed(load_incidents()["INC-008"])
        with self.assertRaisesRegex(ToolError, "EVIDENCE_CONFLICT"):
            validate_submission(
                result("application_regression", ["log-app", "deploy-app"]), seen, gateway
            )

    def test_pool_exhaustion_requires_actual_saturation_and_queue_metrics(self):
        for id in ("CH-003", "CH-005"):
            incident = load_incidents("challenge")[id]
            gateway, seen = observed(incident)
            with (
                self.subTest(id=id),
                self.assertRaisesRegex(ToolError, "INSUFFICIENT_EVIDENCE|recent"),
            ):
                validate_submission(result("resource_exhaustion", list(seen)), seen, gateway)

    def test_additional_scenarios_with_recognized_evidence_are_supported(self):
        for id, cause in (
            ("CH-004", "resource_exhaustion"),
            ("CH-009", "dependency_timeout"),
            ("CH-010", "application_regression"),
        ):
            gateway, seen = observed(load_incidents("challenge")[id])
            with self.subTest(id=id):
                self.assertEqual(
                    cause,
                    validate_submission(result(cause, list(seen)), seen, gateway)[
                        "suspected_cause"
                    ],
                )

    def test_change_must_precede_the_error_and_be_recent(self):
        for id in ("CH-001", "CH-002", "CH-008"):
            gateway, seen = observed(load_incidents("challenge")[id])
            cause = "invalid_configuration" if id == "CH-001" else "application_regression"
            with self.subTest(id=id), self.assertRaisesRegex(ToolError, "INSUFFICIENT_EVIDENCE"):
                validate_submission(result(cause, list(seen)), seen, gateway)

    def test_runbooks_and_quoted_log_instructions_cannot_create_signals(self):
        for id in ("CH-006", "CH-012"):
            incident = load_incidents("challenge")[id]
            from dataclasses import asdict

            assessment = assess_evidence(incident, [asdict(record) for record in incident.records])
            self.assertEqual("insufficient", assessment["decision"])

    def test_a_hypothesis_must_cite_the_corroborating_record(self):
        gateway, seen = observed(load_incidents()["INC-007"])
        with self.assertRaisesRegex(ToolError, "MISSING_SUPPORTING_CITATIONS"):
            validate_submission(result("resource_exhaustion", ["log-pool"]), seen, gateway)

    def test_abstention_remains_valid_when_a_telemetry_tool_is_unavailable(self):
        gateway, seen = observed(load_incidents("challenge")["CH-011"])
        self.assertEqual(
            "abstained",
            validate_submission(result(None, list(seen), "abstained"), seen, gateway)["status"],
        )

    def test_unsupported_event_formats_abstain_instead_of_guessed_matching(self):
        incident = load_incidents()["INC-002"]
        changed = replace(
            incident,
            records=tuple(
                replace(record, text="INFO no UPSTREAM_TIMEOUT detected")
                if record.kind == "log"
                else record
                for record in incident.records
            ),
        )
        gateway, seen = observed(changed)
        self.assertEqual("insufficient", assess_evidence(changed, list(seen.values()))["decision"])
