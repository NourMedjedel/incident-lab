"""Explicit diagnostic rules: a baseline to beat, not an LLM agent."""

from dataclasses import dataclass
from datetime import timedelta
from time import perf_counter

from .models import Incident, instant
from .tools import ToolError, ToolGateway


@dataclass(frozen=True)
class Rule:
    cause: str
    signature: str
    deployment_marker: str | None
    explanation: str
    next_step: str


RULES = (
    Rule(
        "invalid_configuration",
        "CONFIG_VALIDATION_FAILED",
        "configuration",
        "A configuration validation error follows a configuration change.",
        "Check the configuration diff and propose reverting the invalid setting.",
    ),
    Rule(
        "dependency_timeout",
        "UPSTREAM_TIMEOUT",
        None,
        "The service records timeouts while calling an upstream dependency.",
        "Check upstream health before proposing a local restart.",
    ),
    Rule(
        "application_regression",
        "UNHANDLED_EXCEPTION",
        "application",
        "An application exception follows a recent application release.",
        "Inspect the release diff and propose a rollback after operator review.",
    ),
)


def investigate(incident: Incident, *, gateway: ToolGateway | None = None) -> dict:
    started = perf_counter()
    if gateway is not None and gateway.incident != incident:
        raise ValueError("Evidence gateway and incident must match")
    gateway = gateway or ToolGateway(incident)
    errors = []

    def collect(name: str, **kwargs) -> list[dict]:
        try:
            return gateway.call(name, service=incident.service, **kwargs)
        except ToolError as error:
            errors.append(str(error))
            return []

    logs = collect("get_logs")
    metrics = collect("get_metrics")
    deployments = collect("get_deployments")
    candidates = []
    for rule in RULES:
        matching_logs = [
            r
            for r in logs
            if rule.signature in r["text"]
            and timedelta(0)
            <= instant(incident.cutoff) - instant(r["timestamp"])
            <= timedelta(minutes=15)
        ]
        if not matching_logs:
            continue
        supporting_deployments = []
        if rule.deployment_marker:
            for deployment in deployments:
                if rule.deployment_marker not in deployment["text"].lower():
                    continue
                if any(
                    timedelta(0)
                    <= instant(log["timestamp"]) - instant(deployment["timestamp"])
                    <= timedelta(minutes=15)
                    for log in matching_logs
                ):
                    supporting_deployments.append(deployment)
            if not supporting_deployments:
                continue
        candidates.append((rule, matching_logs + supporting_deployments))

    # Missing telemetry can hide contradictory evidence. This baseline abstains
    # rather than treating unavailable observations as reassuring negatives.
    selected = candidates[0] if len(candidates) == 1 and not errors else None
    if selected:
        rule, evidence = selected
        cause, explanation, next_step = rule.cause, rule.explanation, rule.next_step
        query = f"{rule.signature} {rule.cause.replace('_', ' ')}"
    else:
        cause, evidence = None, []
        explanation = (
            "Evidence tools are unavailable; the investigation is incomplete."
            if errors
            else "Conflicting diagnostic signatures require a human investigation."
            if len(candidates) > 1
            else "Available evidence does not support a diagnosis covered by these rules."
        )
        next_step = "Collect additional logs and dependency health before recommending a change."
        query = "incident investigation missing evidence"

    documents = collect("search_runbooks", query=query, limit=2)
    return {
        "incident_id": incident.id,
        "service": incident.service,
        "as_of": incident.cutoff,
        "engine": "rules-v1",
        "mode": getattr(gateway, "mode", "synthetic-fixture-replay"),
        "evidence_source": gateway.describe(),
        "status": "hypothesis" if selected else "abstained",
        "suspected_cause": cause,
        "explanation": explanation,
        "next_step": next_step,
        "evidence_ids": [record["id"] for record in evidence],
        "evidence": evidence,
        "runbooks": documents,
        "observations": {"logs": logs, "metrics": metrics, "deployments": deployments},
        "tool_errors": errors,
        "trace": gateway.trace,
        "measurement": {
            "duration_ms": round((perf_counter() - started) * 1000, 3),
            "llm_calls": 0,
            "llm_cost_usd": 0,
        },
        "limitations": [
            "Fixed rules detect selected signatures; this is not an LLM agent.",
            "Temporal correlation is not proof of root cause.",
            "Runbook text is retrieved as data and never executed.",
            "No remediation is executed.",
        ],
    }
