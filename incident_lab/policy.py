"""Conservative evidence contracts, independent of model prose and expected labels."""

import re
from datetime import timedelta

from .models import Incident, instant

POLICY_VERSION = "evidence-v1"
WINDOW = timedelta(minutes=15)
EVENTS = {
    "CONFIG_VALIDATION_FAILED": "invalid_configuration",
    "UPSTREAM_TIMEOUT": "dependency_timeout",
    "UNHANDLED_EXCEPTION": "application_regression",
    "CONNECTION_POOL_EXHAUSTED": "resource_exhaustion",
}


def numeric_fields(text: str) -> dict[str, float]:
    return {
        key: float(value)
        for key, value in re.findall(r"\b([a-z][a-z0-9_]*)=(-?(?:\d+(?:\.\d*)?|\.\d+))\b", text)
    }


def assess_evidence(incident: Incident, records: list[dict]) -> dict:
    """Recognized log events are necessary evidence, not a general root-cause oracle.

    Only recent telemetry can support a diagnosis. Runbook wording and quoted
    user input cannot create diagnostic signals. Unknown event formats abstain.
    """
    recent = [
        record
        for record in records
        if record["service"] == incident.service
        and timedelta(0) <= instant(incident.cutoff) - instant(record["timestamp"]) <= WINDOW
    ]
    logs = [record for record in recent if record["kind"] == "log"]
    resolutions = [
        record for record in logs if record["text"].startswith("INFO CONFIG_RECOVERY_CONFIRMED:")
    ]
    deployments = [record for record in recent if record["kind"] == "deployment"]
    metrics = [record for record in recent if record["kind"] == "metric"]
    candidates: dict[str, set[str]] = {}
    supporting_sets: dict[str, list[list[str]]] = {}
    for log in logs:
        event = re.match(r"^ERROR\s+([A-Z_]+)(?=[:\s]|$)", log["text"])
        if not event or event[1] not in EVENTS:
            continue
        cause = EVENTS[event[1]]
        if cause == "invalid_configuration" and any(
            instant(item["timestamp"]) >= instant(log["timestamp"]) for item in resolutions
        ):
            continue
        support = {log["id"]}
        if cause in {"invalid_configuration", "application_regression"}:
            marker = "configuration" if cause == "invalid_configuration" else "application"
            changes = [
                item
                for item in deployments
                if marker in item["text"].lower()
                and timedelta(0) <= instant(log["timestamp"]) - instant(item["timestamp"]) <= WINDOW
            ]
            if not changes:
                continue
            support.add(max(changes, key=lambda item: instant(item["timestamp"]))["id"])
        if cause == "resource_exhaustion":
            corroborating = []
            for metric in metrics:
                fields = numeric_fields(metric["text"])
                maximum = fields.get("db_connections_max", 0)
                if (
                    maximum > 0
                    and fields.get("db_connections_busy", -1) >= maximum
                    and fields.get("queue_depth", 0) > 0
                ):
                    corroborating.append(metric)
            if not corroborating:
                continue
            support.add(max(corroborating, key=lambda item: instant(item["timestamp"]))["id"])
        candidates.setdefault(cause, set()).update(support)
        supporting_sets.setdefault(cause, []).append(sorted(support))
    return {
        "version": POLICY_VERSION,
        "supported_candidates": {cause: sorted(ids) for cause, ids in candidates.items()},
        "supporting_sets": supporting_sets,
        "decision": "supported"
        if len(candidates) == 1
        else "conflicting"
        if candidates
        else "insufficient",
        "limitations": "Minimum recognized evidence contract; not semantic verification or proof of causality.",
    }
