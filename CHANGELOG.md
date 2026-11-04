# Changelog

## 0.2.0 - unreleased reliability milestone

- Backend evidence contracts and abstention-only routing for insufficient, conflicting, or unavailable primary telemetry.
- Bounded correction of text-only responses and invalid submissions, with failures preserved when budgets expire.
- Twelve additional project-authored challenge cases, separate suite hashes, and backward-compatible replay of the original results.
- A real SQLite-backed local HTTP orders service, coherent observation snapshots, and a read-only HTTP evidence adapter.
- A separate operator workflow for parameter-bound, expiring approval and one allowlisted configuration restoration.
- Durable revision checks, idempotent/concurrent execution control, audit history, and actual HTTP recovery verification.
- Tests for service failures, timeouts, authorization, stale/expired approvals, parameter changes, retries, and restart persistence.

## 0.1.0 - initial public version

- Reproducible synthetic incident fixtures with a rules investigator and BM25 runbook search.
- Service-scoped, incident-time evidence tools with call budgets and traces.
- A bounded LangGraph investigator with Groq, local Ollama, and Anthropic adapters.
- Backend validation for result schemas, fetched citations, and telemetry availability.
- Baseline evaluation, real-model comparison, and offline replay of recorded predictions.
- An inspectable local Qwen3-8B run, including unsupported diagnoses and a protocol failure.
- Locked dependencies, formatting/lint checks, tests, package metadata, and CI configuration.

This version was a fixture-based development lab. Real service adapters, remediation, Kubernetes deployment, and a held-out benchmark were outside its scope.
