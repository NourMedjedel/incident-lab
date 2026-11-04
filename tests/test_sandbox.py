import io
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from incident_lab.baseline import investigate
from incident_lab.cli import main
from incident_lab.live import HTTPToolGateway, local_url, request_json, running_sandbox
from incident_lab.sandbox import SandboxError, SandboxStore
from incident_lab.tools import ToolError


class StoreTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1_800_000_000.0
        self.store = SandboxStore(self.temp.name, clock=lambda: self.now)
        self.store.inject("invalid_configuration")
        self.store.request_orders()
        snapshot = self.store.snapshot()
        self.proposal = self.store.propose(snapshot["id"])

    def test_unapproved_execution_is_rejected(self):
        with self.assertRaisesRegex(SandboxError, "approval"):
            self.store.execute(self.proposal["id"], self.proposal["parameters"], "test")
        self.assertEqual(503, self.store.request_orders()[0])

    def test_approved_parameters_cannot_be_changed(self):
        self.store.approve(self.proposal["id"], 60)
        changed = {**self.proposal["parameters"], "service": "another-service"}
        with self.assertRaisesRegex(SandboxError, "parameters"):
            self.store.execute(self.proposal["id"], changed, "test")
        self.assertEqual(503, self.store.request_orders()[0])

    def test_expired_approval_is_not_authorization(self):
        self.store.approve(self.proposal["id"], 1)
        self.now += 2
        with self.assertRaisesRegex(SandboxError, "expired"):
            self.store.execute(self.proposal["id"], self.proposal["parameters"], "test")

    def test_changed_revision_invalidates_approval(self):
        self.store.approve(self.proposal["id"], 60)
        self.store.inject("invalid_configuration")
        with self.assertRaisesRegex(SandboxError, "State changed"):
            self.store.execute(self.proposal["id"], self.proposal["parameters"], "test")

    def test_retry_is_idempotent_and_another_key_cannot_reexecute(self):
        self.store.approve(self.proposal["id"], 60)
        first = self.store.execute(self.proposal["id"], self.proposal["parameters"], "test")
        second = self.store.execute(self.proposal["id"], self.proposal["parameters"], "test")
        self.assertEqual(first["revision"], second["revision"])
        self.assertTrue(second["replayed"])
        with self.assertRaisesRegex(SandboxError, "another idempotency"):
            self.store.execute(self.proposal["id"], self.proposal["parameters"], "another")

    def test_concurrent_execution_applies_exactly_one_state_change(self):
        self.store.approve(self.proposal["id"], 60)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda _: self.store.execute(
                        self.proposal["id"], self.proposal["parameters"], "same-key"
                    ),
                    range(2),
                )
            )
        self.assertEqual([False, True], sorted(result["replayed"] for result in results))
        self.assertEqual(
            1,
            sum(event["event"] == "configuration_restored" for event in self.store.audit_events()),
        )

    def test_restart_preserves_tokens_approvals_and_execution_history(self):
        self.store.approve(self.proposal["id"], 60)
        restarted = SandboxStore(self.temp.name, clock=lambda: self.now)
        self.assertEqual(self.store.tokens, restarted.tokens)
        result = restarted.execute(self.proposal["id"], self.proposal["parameters"], "test")
        self.assertEqual("executed", result["status"])
        again = SandboxStore(self.temp.name, clock=lambda: self.now)
        self.assertTrue(
            again.execute(self.proposal["id"], self.proposal["parameters"], "test")["replayed"]
        )

    def test_ttl_bounds_are_enforced(self):
        for ttl in (0, 301, True):
            with self.subTest(ttl=ttl), self.assertRaises(SandboxError):
                self.store.approve(self.proposal["id"], ttl)

    def test_an_old_snapshot_cannot_be_approved_even_with_unchanged_revision(self):
        self.now += 301
        with self.assertRaisesRegex(SandboxError, "Snapshot expired"):
            self.store.approve(self.proposal["id"], 60)


class HTTPTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SandboxStore(self.temp.name)
        context = running_sandbox(self.store)
        self.server = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)

    def post(self, path, body, role="operator"):
        return request_json(
            self.server.url,
            path,
            method="POST",
            body=body,
            token=self.store.tokens[role] if role else None,
        )

    def broken_proposal(self):
        self.post("/control/inject", {"fault": "invalid_configuration"})
        self.assertEqual(503, request_json(self.server.url, "/orders")[0])
        gateway = HTTPToolGateway(self.server.url)
        result = investigate(gateway.incident, gateway=gateway)
        self.assertEqual("invalid_configuration", result["suspected_cause"])
        status, proposal = self.post(
            "/control/proposals", {"snapshot_id": gateway.snapshot_id}, "executor"
        )
        self.assertEqual(200, status)
        return gateway, proposal

    def test_real_http_failure_then_approved_recovery_is_verified(self):
        self.assertEqual(200, request_json(self.server.url, "/orders")[0])
        gateway, proposal = self.broken_proposal()
        payload = {
            "proposal_id": proposal["id"],
            "parameters": proposal["parameters"],
            "idempotency_key": "one",
        }
        self.assertEqual(409, self.post("/control/execute", payload, "executor")[0])
        self.assertEqual(
            200,
            self.post("/control/approve", {"proposal_id": proposal["id"], "ttl_seconds": 60})[0],
        )
        status, execution = self.post("/control/execute", payload, "executor")
        self.assertEqual(200, status)
        self.assertEqual([200, 200, 200], execution["verification"]["statuses"])
        self.assertTrue(self.post("/control/execute", payload, "executor")[1]["replayed"])
        self.assertEqual("live-sandbox-snapshot", gateway.mode)
        recovered = HTTPToolGateway(self.server.url)
        from incident_lab.policy import assess_evidence

        records = []
        for tool in ("get_logs", "get_metrics", "get_deployments"):
            records.extend(recovered.call(tool, service="orders-api"))
        self.assertEqual("insufficient", assess_evidence(recovered.incident, records)["decision"])
        self.assertTrue(
            any(event["event"] == "control_rejected" for event in self.store.audit_events())
        )

    def test_roles_cannot_approve_or_execute_as_each_other(self):
        _, proposal = self.broken_proposal()
        self.assertEqual(
            403,
            self.post(
                "/control/approve", {"proposal_id": proposal["id"], "ttl_seconds": 60}, "executor"
            )[0],
        )
        self.assertEqual(
            403,
            self.post(
                "/control/execute",
                {
                    "proposal_id": proposal["id"],
                    "parameters": proposal["parameters"],
                    "idempotency_key": "test",
                },
                "operator",
            )[0],
        )

    def test_unknown_request_fields_and_missing_credentials_are_rejected(self):
        self.assertEqual(
            403, self.post("/control/inject", {"fault": "invalid_configuration"}, None)[0]
        )
        self.assertEqual(
            400,
            self.post("/control/inject", {"fault": "invalid_configuration", "shell": "anything"})[
                0
            ],
        )
        self.assertEqual(400, self.post("/control/proposals", {"snapshot_id": []}, "executor")[0])

    def test_snapshot_is_consistent_even_when_control_state_changes(self):
        gateway, _ = self.broken_proposal()
        original = gateway.call("get_deployments", service="orders-api")
        self.post("/control/inject", {"fault": "invalid_configuration"})
        self.assertEqual(original, gateway.call("get_deployments", service="orders-api"))
        self.assertEqual(
            409,
            self.post("/control/proposals", {"snapshot_id": gateway.snapshot_id}, "executor")[0],
        )

    def test_actual_telemetry_503_is_visible_to_the_investigator(self):
        self.post("/control/inject", {"fault": "invalid_configuration"})
        request_json(self.server.url, "/orders")
        self.post("/control/inject", {"fault": "telemetry_outage"})
        gateway = HTTPToolGateway(self.server.url)
        result = investigate(gateway.incident, gateway=gateway)
        self.assertEqual("abstained", result["status"])
        self.assertIn("503", result["tool_errors"][0])

    def test_real_http_timeout_is_bounded_and_traced(self):
        self.post("/control/inject", {"fault": "slow_telemetry"})
        gateway = HTTPToolGateway(self.server.url)
        gateway.timeout = 0.03
        with self.assertRaisesRegex(ToolError, "timed out"):
            gateway.call("get_logs", service="orders-api")
        self.assertEqual("error", gateway.trace[-1]["status"])

    def test_adapter_rejects_cross_service_or_future_payloads(self):
        gateway = HTTPToolGateway(self.server.url)
        response = {
            "snapshot_id": gateway.snapshot_id,
            "service": "orders-api",
            "revision": gateway.revision,
            "records": [
                {
                    "id": "bad",
                    "kind": "log",
                    "service": "other-service",
                    "timestamp": gateway.incident.cutoff,
                    "text": "bad record",
                }
            ],
        }
        with (
            patch("incident_lab.live.request_json", return_value=(200, response)),
            self.assertRaises(ToolError),
        ):
            gateway.call("get_logs", service="orders-api")

    def test_adapter_rejects_future_records_and_mixed_snapshot_revisions(self):
        from datetime import timedelta

        from incident_lab.models import instant

        gateway = HTTPToolGateway(self.server.url)
        response = {
            "snapshot_id": gateway.snapshot_id,
            "service": "orders-api",
            "revision": gateway.revision,
            "records": [
                {
                    "id": "future",
                    "kind": "log",
                    "service": "orders-api",
                    "timestamp": (
                        instant(gateway.incident.cutoff) + timedelta(seconds=1)
                    ).isoformat(),
                    "text": "ERROR CONFIG_VALIDATION_FAILED: not yet observed",
                }
            ],
        }
        with (
            patch("incident_lab.live.request_json", return_value=(200, response)),
            self.assertRaises(ToolError),
        ):
            gateway.call("get_logs", service="orders-api")
        response["records"] = []
        response["revision"] += 1
        with (
            patch("incident_lab.live.request_json", return_value=(200, response)),
            self.assertRaises(ToolError),
        ):
            gateway.call("get_logs", service="orders-api")

    def test_nonlocal_origins_are_refused_before_any_request(self):
        for url in (
            "https://example.com:443",
            "http://127.0.0.1:8765/path",
            "http://user:secret@127.0.0.1:8765",
        ):
            with self.subTest(url=url), self.assertRaises(SandboxError):
                local_url(url)


class DemoTests(TestCase):
    def test_demo_requires_explicit_approval_and_does_not_expose_tokens(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            path = Path(directory) / "demo.json"
            self.assertEqual(
                0, main(["sandbox", "demo", "--state-dir", directory, "--output", str(path)])
            )
            result = json.loads(path.read_text())
            self.assertNotIn("execution", result)
            self.assertEqual([503, 503, 503], result["during_fault"])
            for token_file in Path(result["state_directory"]).glob("*.token"):
                self.assertNotIn(token_file.read_text().strip(), path.read_text())

    def test_approved_demo_exercises_complete_http_workflow(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            path = Path(directory) / "demo.json"
            self.assertEqual(
                0,
                main(
                    [
                        "sandbox",
                        "demo",
                        "--approve",
                        "--state-dir",
                        directory,
                        "--output",
                        str(path),
                    ]
                ),
            )
            result = json.loads(path.read_text())
            self.assertEqual([200, 200, 200], result["after_recovery"])
            self.assertTrue(result["execution"]["verification"]["recovered"])
