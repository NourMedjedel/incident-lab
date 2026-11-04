# ADR 0003: evidence contracts and a separate supervised sandbox actuator

Status: accepted for version 0.2.

## Context

The first local model run diagnosed pool exhaustion but also guessed on insufficient and conflicting evidence. A telemetry outage led to an invalid final response. Citation provenance alone was not enough. Recovery demonstrations also needed an actual service boundary rather than a prewritten success record.

## Decision

Validate minimum cause-specific telemetry contracts in the backend and require abstention on unresolved competing signals. Allow bounded correction of recoverable response errors while preserving explicit execution failures. Keep the original rules, fixtures, and recorded predictions for comparison.

Add a local SQLite-backed HTTP service and immutable evidence snapshots. Keep recovery capabilities outside the model's tools. A separate operator workflow approves exact stored parameters, then an executor role applies one known configuration restoration with freshness, expiry, revision, and idempotency checks in a transaction. Verify the result using actual HTTP requests.

## Consequences

Unsupported hypotheses can be blocked without trusting model confidence or prose. Recognized telemetry formats are an explicit limitation; the evidence policy is not a general root-cause classifier. The challenge suite is project-authored, so independent evaluation remains necessary.

The sandbox exercises network and durable-state behavior without a cloud bill. Local role tokens demonstrate control boundaries but do not provide production IAM or independence between people using the same OS account. The actuator cannot run arbitrary commands or alter external infrastructure.
