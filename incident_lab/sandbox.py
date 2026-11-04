"""Local HTTP service and durable, operator-approved configuration recovery.

All state is synthetic. This module never runs shell commands or contacts an
enterprise system. A local OS user can access both demo roles; production IAM
and multi-user authorization are outside this sandbox's trust boundary.
"""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

SERVICE = "orders-api"
ACTION = "restore_configuration"


class SandboxError(ValueError):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def fingerprint(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


class SandboxStore:
    def __init__(self, directory: str | Path, *, clock=time.time):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = self.directory / "control.sqlite3"
        self.clock = clock
        self.tokens = {role: self._token(role) for role in ("operator", "executor")}
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS evidence (id TEXT PRIMARY KEY, kind TEXT, timestamp TEXT, text TEXT);
                CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, parameters TEXT, digest TEXT,
                    status TEXT, expires REAL, idempotency_key TEXT, result TEXT);
                CREATE TABLE IF NOT EXISTS audit (sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT, actor TEXT, event TEXT, data TEXT);
            """)
            if db.execute("SELECT 1 FROM state WHERE id=1").fetchone() is None:
                self.write_state(
                    db,
                    {
                        "revision": 1,
                        "database_url": "sqlite:///orders.sqlite3",
                        "requests": 0,
                        "errors": 0,
                        "telemetry_down": False,
                        "telemetry_delay": 0,
                    },
                )
                self.record(
                    db,
                    "deployment",
                    "Configuration deployment initial established a known-good DATABASE_URL.",
                )
        with sqlite3.connect(self.directory / "orders.sqlite3") as db:
            db.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, status TEXT)")
            db.execute("INSERT OR IGNORE INTO orders VALUES (1, 'ready')")

    def _token(self, role: str) -> str:
        path = self.directory / f"{role}.token"
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            token = path.read_text(encoding="utf-8").strip()
            if len(token) < 32:
                raise SandboxError(
                    "Invalid local role token; use a new sandbox state directory", 400
                )
            return token
        token = secrets.token_urlsafe(32)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(token + "\n")
        return token

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.database, timeout=3, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            if db.in_transaction:
                db.commit()
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def timestamp(self):
        return datetime.fromtimestamp(self.clock(), timezone.utc).isoformat()

    def audit(self, db, actor: str, event: str, data: dict):
        db.execute(
            "INSERT INTO audit(timestamp,actor,event,data) VALUES (?,?,?,?)",
            (self.timestamp(), actor, event, json.dumps(data, sort_keys=True)),
        )

    def authenticate(self, header: str, role: str):
        supplied = header.removeprefix("Bearer ")
        if (
            not supplied.isascii()
            or not header.startswith("Bearer ")
            or not hmac.compare_digest(supplied, self.tokens[role])
        ):
            raise SandboxError(f"A valid {role} role token is required", 403)

    @staticmethod
    def read_state(db):
        return json.loads(db.execute("SELECT data FROM state WHERE id=1").fetchone()["data"])

    @staticmethod
    def write_state(db, state):
        db.execute("INSERT OR REPLACE INTO state VALUES (1,?)", (json.dumps(state),))

    def record(self, db, kind: str, text: str):
        db.execute(
            "INSERT INTO evidence VALUES (?,?,?,?)",
            (f"{kind}-{uuid4().hex}", kind, self.timestamp(), text),
        )

    def request_orders(self) -> tuple[int, dict]:
        with self.transaction() as db:
            state = self.read_state(db)
            state["requests"] += 1
            if state["database_url"] != "sqlite:///orders.sqlite3":
                state["errors"] += 1
                self.record(
                    db,
                    "log",
                    "ERROR CONFIG_VALIDATION_FAILED: DATABASE_URL has unsupported scheme.",
                )
                status, payload = 503, {"error": "configuration_invalid", "service": SERVICE}
            else:
                with sqlite3.connect(self.directory / "orders.sqlite3") as business:
                    rows = business.execute("SELECT id,status FROM orders").fetchall()
                status, payload = (
                    200,
                    {
                        "service": SERVICE,
                        "orders": [{"id": id, "status": value} for id, value in rows],
                    },
                )
            self.write_state(db, state)
            return status, payload

    def inject(self, fault: str) -> dict:
        if fault not in {"invalid_configuration", "telemetry_outage", "slow_telemetry"}:
            raise SandboxError("Unknown sandbox fault", 400)
        with self.transaction() as db:
            state = self.read_state(db)
            state["revision"] += 1
            if fault == "invalid_configuration":
                state["database_url"] = "broken:///orders.sqlite3"
                self.record(
                    db,
                    "deployment",
                    f"Configuration deployment cfg-{state['revision']} changed DATABASE_URL.",
                )
            elif fault == "telemetry_outage":
                state["telemetry_down"] = True
            else:
                state["telemetry_delay"] = 0.25
            self.write_state(db, state)
            self.audit(
                db, "operator", "fault_injected", {"fault": fault, "revision": state["revision"]}
            )
            return {"fault": fault, "revision": state["revision"]}

    def snapshot(self) -> dict:
        with self.transaction() as db:
            state = self.read_state(db)
            cutoff = self.timestamp()
            rows = db.execute(
                "SELECT * FROM evidence ORDER BY timestamp DESC,id DESC LIMIT 100"
            ).fetchall()
            records = [{**dict(row), "service": SERVICE} for row in rows]
            ratio = state["errors"] / state["requests"] if state["requests"] else 0
            records += [
                {
                    "id": f"metric-{uuid4().hex}",
                    "kind": "metric",
                    "service": SERVICE,
                    "timestamp": cutoff,
                    "text": f"http_error_ratio={ratio}; request_count={state['requests']}; error_count={state['errors']}",
                },
                {
                    "id": "configuration-live@1",
                    "kind": "runbook",
                    "service": SERVICE,
                    "timestamp": cutoff,
                    "text": "CONFIG_VALIDATION_FAILED: inspect the configuration change. Restore known-good configuration only after an operator approves the exact proposal; verify real /orders requests afterward.",
                },
            ]
            id = uuid4().hex
            value = {
                "id": id,
                "service": SERVICE,
                "title": "Orders service availability investigation",
                "cutoff": cutoff,
                "revision": state["revision"],
                "records": records,
                "telemetry_down": state["telemetry_down"],
                "telemetry_delay": state["telemetry_delay"],
            }
            db.execute("INSERT INTO snapshots VALUES (?,?)", (id, json.dumps(value)))
            self.audit(
                db, "reader", "snapshot_created", {"snapshot_id": id, "revision": state["revision"]}
            )
            return {key: value[key] for key in ("id", "service", "title", "cutoff", "revision")}

    def get_snapshot(self, id: str) -> dict:
        with self.transaction() as db:
            row = db.execute("SELECT data FROM snapshots WHERE id=?", (id,)).fetchone()
            if row is None:
                raise SandboxError("Unknown snapshot", 404)
            return json.loads(row["data"])

    def propose(self, snapshot_id: str) -> dict:
        snapshot = self.get_snapshot(snapshot_id)
        from .models import Incident
        from .policy import assess_evidence

        assessment = assess_evidence(
            Incident(snapshot_id, SERVICE, snapshot["title"], snapshot["cutoff"], ()),
            snapshot["records"],
        )
        if (
            snapshot["telemetry_down"]
            or assessment["decision"] != "supported"
            or "invalid_configuration" not in assessment["supported_candidates"]
        ):
            raise SandboxError("The snapshot does not support configuration recovery")
        with self.transaction() as db:
            state = self.read_state(db)
            self.require_fresh_snapshot(db, snapshot_id)
            if state["revision"] != snapshot["revision"]:
                raise SandboxError("Snapshot revision is stale; investigate again")
            if state["database_url"] == "sqlite:///orders.sqlite3":
                raise SandboxError("Configuration is already healthy")
            parameters = {
                "action": ACTION,
                "service": SERVICE,
                "snapshot_id": snapshot_id,
                "expected_revision": state["revision"],
                "target_configuration": "known-good-initial",
            }
            id = uuid4().hex
            digest = fingerprint(parameters)
            db.execute(
                "INSERT INTO proposals VALUES (?,?,?,'pending',NULL,NULL,NULL)",
                (id, json.dumps(parameters, sort_keys=True), digest),
            )
            self.audit(db, "executor", "proposal_created", {"proposal_id": id, "digest": digest})
            return {"id": id, "parameters": parameters, "fingerprint": digest, "status": "pending"}

    def proposal(self, id: str) -> dict:
        with self.transaction() as db:
            row = db.execute("SELECT * FROM proposals WHERE id=?", (id,)).fetchone()
            if row is None:
                raise SandboxError("Unknown proposal", 404)
            return {
                "id": id,
                "parameters": json.loads(row["parameters"]),
                "fingerprint": row["digest"],
                "status": row["status"],
                "expires": row["expires"],
            }

    def require_fresh_snapshot(self, db, snapshot_id: str):
        row = db.execute("SELECT data FROM snapshots WHERE id=?", (snapshot_id,)).fetchone()
        if row is None:
            raise SandboxError("Unknown snapshot", 404)
        cutoff = datetime.fromisoformat(json.loads(row["data"])["cutoff"]).timestamp()
        if not 0 <= self.clock() - cutoff <= 300:
            raise SandboxError(
                "Snapshot expired; collect fresh evidence before proposing or executing recovery"
            )

    def approve(self, id: str, ttl: int) -> dict:
        if type(ttl) is not int or not 1 <= ttl <= 300:
            raise SandboxError("Approval TTL must be 1-300 seconds", 400)
        with self.transaction() as db:
            row = db.execute("SELECT * FROM proposals WHERE id=?", (id,)).fetchone()
            if row is None or row["status"] != "pending":
                raise SandboxError("Only a pending proposal can be approved")
            parameters = json.loads(row["parameters"])
            self.require_fresh_snapshot(db, parameters["snapshot_id"])
            if self.read_state(db)["revision"] != parameters["expected_revision"]:
                raise SandboxError("Proposal revision is stale")
            expires = self.clock() + ttl
            db.execute("UPDATE proposals SET status='approved',expires=? WHERE id=?", (expires, id))
            self.audit(
                db,
                "operator",
                "proposal_approved",
                {"proposal_id": id, "digest": row["digest"], "expires": expires},
            )
            return {
                "id": id,
                "status": "approved",
                "expires": expires,
                "fingerprint": row["digest"],
            }

    def execute(self, id: str, parameters: dict, key: str) -> dict:
        if not isinstance(key, str) or not 1 <= len(key) <= 100:
            raise SandboxError("An idempotency key of 1-100 characters is required", 400)
        with self.transaction() as db:
            row = db.execute("SELECT * FROM proposals WHERE id=?", (id,)).fetchone()
            if row is None:
                raise SandboxError("Unknown proposal", 404)
            if not isinstance(parameters, dict) or fingerprint(parameters) != row["digest"]:
                raise SandboxError("Execution parameters differ from the approved proposal")
            if row["status"] == "executed":
                if row["idempotency_key"] != key:
                    raise SandboxError("Proposal already executed with another idempotency key")
                return {**json.loads(row["result"]), "replayed": True}
            if row["status"] != "approved":
                raise SandboxError("Operator approval is required before execution")
            if self.clock() >= row["expires"]:
                raise SandboxError("Approval expired", 410)
            self.require_fresh_snapshot(db, parameters["snapshot_id"])
            state = self.read_state(db)
            if state["revision"] != parameters["expected_revision"]:
                raise SandboxError("State changed after approval; create a new proposal")
            state["database_url"] = "sqlite:///orders.sqlite3"
            state["revision"] += 1
            self.write_state(db, state)
            self.record(
                db,
                "deployment",
                f"Configuration deployment cfg-{state['revision']} restored known-good DATABASE_URL.",
            )
            result = {
                "proposal_id": id,
                "status": "executed",
                "revision": state["revision"],
                "fingerprint": row["digest"],
                "replayed": False,
            }
            db.execute(
                "UPDATE proposals SET status='executed',idempotency_key=?,result=? WHERE id=?",
                (key, json.dumps(result), id),
            )
            self.audit(db, "executor", "configuration_restored", result)
            return result

    def record_verification(self, id: str, statuses: list[int]) -> dict:
        with self.transaction() as db:
            row = db.execute(
                "SELECT result FROM proposals WHERE id=? AND status='executed'", (id,)
            ).fetchone()
            if row is None:
                raise SandboxError("No execution to verify")
            result = json.loads(row["result"])
            if "verification" not in result:
                result["verification"] = {
                    "statuses": statuses,
                    "recovered": len(statuses) == 3 and all(status == 200 for status in statuses),
                    "timestamp": self.timestamp(),
                }
                db.execute("UPDATE proposals SET result=? WHERE id=?", (json.dumps(result), id))
                self.audit(
                    db,
                    "verifier",
                    "recovery_checked",
                    {"proposal_id": id, **result["verification"]},
                )
                if result["verification"]["recovered"]:
                    self.record(
                        db,
                        "log",
                        "INFO CONFIG_RECOVERY_CONFIRMED: approved configuration restoration passed three actual HTTP probes.",
                    )
            return result

    def audit_events(self) -> list[dict]:
        with self.transaction() as db:
            return [
                {**dict(row), "data": json.loads(row["data"])}
                for row in db.execute("SELECT * FROM audit ORDER BY sequence").fetchall()
            ]

    def record_rejection(self, path: str, error: SandboxError):
        with self.transaction() as db:
            self.audit(
                db,
                "request",
                "control_rejected",
                {"path": path[:160], "status": error.status, "reason": str(error)[:300]},
            )
