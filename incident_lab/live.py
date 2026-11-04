"""Loopback HTTP evidence adapter and sandbox API. No action tools reach the LLM."""

import json
import socket
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .models import Incident, Record, instant
from .replay import search_runbooks
from .sandbox import SERVICE, SandboxError, SandboxStore
from .tools import ToolError, ToolGateway


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def local_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise SandboxError(
            "Sandbox URL must be a loopback HTTP origin without credentials or a path", 400
        )
    try:
        if parsed.port is None or not 1 <= parsed.port <= 65535:
            raise ValueError
    except ValueError as error:
        raise SandboxError("Sandbox URL requires a valid explicit port", 400) from error
    return value.rstrip("/")


def request_json(url: str, path: str, *, method="GET", body=None, token=None, timeout=2.0):
    origin = local_url(url)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        origin + path,
        method=method,
        headers=headers,
        data=json.dumps(body, allow_nan=False).encode() if body is not None else None,
    )
    try:
        response = build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout)
    except HTTPError as error:
        response = error
    except (URLError, TimeoutError, socket.timeout) as error:
        raise SandboxError("Local service request failed or timed out", 504) from error
    with response:
        raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise SandboxError("Local service response exceeded its size limit", 502)
        try:
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError) as error:
            raise SandboxError("Local service returned invalid JSON", 502) from error
        return response.code, result


class SandboxHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, store: SandboxStore, port: int = 8765):
        self.store = store
        super().__init__(("127.0.0.1", port), SandboxHandler)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_port}"


class SandboxHandler(BaseHTTPRequestHandler):
    server: SandboxHTTPServer

    def log_message(self, format, *args):
        # Request bodies and authentication headers are never logged.
        pass

    def send_json(self, status: int, payload: dict):
        data = json.dumps(payload, allow_nan=False).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def body(self, fields: set[str]):
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 <= length <= 16384:
            raise SandboxError("Request body is too large", 413)
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict) or set(value) != fields:
            raise SandboxError("Request fields do not match the endpoint schema", 400)
        for key in fields & {"snapshot_id", "proposal_id", "fault", "idempotency_key"}:
            if not isinstance(value[key], str) or not 1 <= len(value[key]) <= 200:
                raise SandboxError(f"Invalid {key}", 400)
        return value

    def do_GET(self):
        try:
            self.handle_get()
        except SandboxError as error:
            self.send_json(error.status, {"error": str(error)})
        except (ValueError, TypeError, KeyError):
            self.send_json(400, {"error": "Invalid request"})

    def handle_get(self):
        path = urlsplit(self.path).path
        store = self.server.store
        if path in {"/orders", "/health"}:
            status, result = store.request_orders()
            self.send_json(status, result)
        elif path == "/v1/audit":
            self.send_json(200, {"events": store.audit_events()})
        elif path.startswith("/control/proposals/"):
            store.authenticate(self.headers.get("Authorization", ""), "executor")
            self.send_json(200, store.proposal(path.split("/")[-1]))
        elif path.startswith("/v1/snapshots/"):
            parts = path.split("/")
            if len(parts) != 5:
                raise SandboxError("Unknown endpoint", 404)
            snapshot = store.get_snapshot(parts[3])
            tool = parts[4]
            if tool == "get_deployments" and snapshot["telemetry_down"]:
                raise SandboxError("Deployment telemetry is unavailable", 503)
            if tool == "get_logs" and snapshot["telemetry_delay"]:
                time.sleep(snapshot["telemetry_delay"])
            if tool == "search_runbooks":
                query = parse_qs(urlsplit(self.path).query)
                term = query.get("query", [""])[0]
                limit = int(query.get("limit", ["3"])[0])
                if not term or len(term) > 500 or not 1 <= limit <= 10:
                    raise SandboxError("Invalid retrieval query", 400)
                from dataclasses import asdict

                incident = Incident(
                    snapshot["id"],
                    SERVICE,
                    snapshot["title"],
                    snapshot["cutoff"],
                    tuple(Record(**record) for record in snapshot["records"]),
                )
                records = [
                    {**asdict(item["record"]), "retrieval_score": item["score"]}
                    for item in search_runbooks(incident, term, limit)
                ]
            else:
                kind = {
                    "get_logs": "log",
                    "get_metrics": "metric",
                    "get_deployments": "deployment",
                }.get(tool)
                if kind is None:
                    raise SandboxError("Unknown evidence tool", 404)
                records = [record for record in snapshot["records"] if record["kind"] == kind]
            self.send_json(
                200,
                {
                    "snapshot_id": snapshot["id"],
                    "service": SERVICE,
                    "revision": snapshot["revision"],
                    "records": records,
                },
            )
        else:
            raise SandboxError("Unknown endpoint", 404)

    def do_POST(self):
        try:
            self.handle_post()
        except SandboxError as error:
            if urlsplit(self.path).path.startswith("/control/"):
                self.server.store.record_rejection(urlsplit(self.path).path, error)
            self.send_json(error.status, {"error": str(error)})
        except (ValueError, TypeError, KeyError):
            self.send_json(400, {"error": "Invalid request"})

    def handle_post(self):
        path = urlsplit(self.path).path
        store = self.server.store
        if path == "/v1/snapshots":
            self.body(set())
            result = store.snapshot()
        elif path == "/control/inject":
            store.authenticate(self.headers.get("Authorization", ""), "operator")
            result = store.inject(self.body({"fault"})["fault"])
        elif path == "/control/proposals":
            store.authenticate(self.headers.get("Authorization", ""), "executor")
            result = store.propose(self.body({"snapshot_id"})["snapshot_id"])
        elif path == "/control/approve":
            store.authenticate(self.headers.get("Authorization", ""), "operator")
            body = self.body({"proposal_id", "ttl_seconds"})
            result = store.approve(body["proposal_id"], body["ttl_seconds"])
        elif path == "/control/execute":
            store.authenticate(self.headers.get("Authorization", ""), "executor")
            body = self.body({"proposal_id", "parameters", "idempotency_key"})
            result = store.execute(body["proposal_id"], body["parameters"], body["idempotency_key"])
            if "verification" not in result:
                statuses = [request_json(self.server.url, "/orders")[0] for _ in range(3)]
                result = {
                    **store.record_verification(body["proposal_id"], statuses),
                    "replayed": result["replayed"],
                }
        else:
            raise SandboxError("Unknown endpoint", 404)
        self.send_json(200, result)


class HTTPToolGateway(ToolGateway):
    mode = "live-sandbox-snapshot"

    def __init__(self, url: str, *, max_calls=8, timeout=2.0):
        self.url = local_url(url)
        self.timeout = timeout
        status, snapshot = request_json(
            self.url, "/v1/snapshots", method="POST", body={}, timeout=timeout
        )
        if status != 200:
            raise SandboxError("Could not create a coherent evidence snapshot", status)
        self.snapshot_id = snapshot["id"]
        self.revision = snapshot["revision"]
        super().__init__(
            Incident(
                snapshot["id"], snapshot["service"], snapshot["title"], snapshot["cutoff"], ()
            ),
            max_calls,
        )

    def describe(self):
        return {
            "kind": "http-snapshot",
            "url": self.url,
            "snapshot_id": self.snapshot_id,
            "state_revision": self.revision,
        }

    def read(self, name: str, arguments: dict) -> list[dict]:
        suffix = (
            "?" + urlencode({"query": arguments["query"], "limit": arguments.get("limit", 3)})
            if name == "search_runbooks"
            else ""
        )
        try:
            status, payload = request_json(
                self.url, f"/v1/snapshots/{self.snapshot_id}/{name}{suffix}", timeout=self.timeout
            )
            if status != 200:
                raise ToolError(f"Evidence endpoint failed with HTTP {status}")
            if (
                payload["snapshot_id"] != self.snapshot_id
                or payload["service"] != self.incident.service
                or payload["revision"] != self.revision
                or not isinstance(payload["records"], list)
                or len(payload["records"]) > 100
            ):
                raise ToolError("Evidence snapshot identity or response size is invalid")
            expected_kind = {
                "get_logs": "log",
                "get_metrics": "metric",
                "get_deployments": "deployment",
                "search_runbooks": "runbook",
            }[name]
            ids = set()
            for raw in payload["records"]:
                record = Record(
                    **{key: raw[key] for key in ("id", "kind", "service", "timestamp", "text")}
                )
                if (
                    record.id in ids
                    or record.service != self.incident.service
                    or record.kind != expected_kind
                    or instant(record.timestamp) > instant(self.incident.cutoff)
                ):
                    raise ToolError(
                        "Evidence violates service, time, kind, or uniqueness boundaries"
                    )
                ids.add(record.id)
            return payload["records"]
        except (SandboxError, ValueError, KeyError, TypeError) as error:
            raise ToolError(f"Live evidence unavailable: {error}") from error


@contextmanager
def running_sandbox(store: SandboxStore):
    server = SandboxHTTPServer(store, port=0)
    worker = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
    worker.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
