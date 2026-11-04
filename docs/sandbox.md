# Live HTTP sandbox and supervised recovery

The sandbox runs an actual loopback HTTP orders service backed by a small SQLite database. It produces real HTTP responses and request-derived telemetry. A separate control API injects faults, captures consistent evidence snapshots, and manages a single allowlisted recovery action.

The workload and data are synthetic. This exercises deployment-style failure and control boundaries locally; it does not establish production scale, independent security review, or operation of a client's infrastructure.

## Fast demonstration, without a model

From the repository root, using Python 3.11+:

```bash
python3 -m incident_lab sandbox demo
```

This starts an ephemeral local server, makes three healthy `/orders` requests, injects an invalid configuration, makes three failing requests, investigates through HTTP tools using the rules baseline, and creates a recovery proposal. Without approval, it does not execute recovery. The ephemeral server stops when the demonstration ends; its state and audit remain under `artifacts/sandbox-demo/`.

Explicitly approve the demo's known-good configuration restoration:

```bash
python3 -m incident_lab sandbox demo --approve
```

Expected sequence:

```text
healthy=[200, 200, 200], fault=[503, 503, 503]
Exact proposed action: ... restore_configuration ...
Approved recovery verified with actual HTTP: [200, 200, 200]
```

The flag is explicit permission for this isolated demo action. It automates the approval step using the demo's operator token; it is not evidence of a separate person reviewing a model's recommendation. Use the manual workflow below to inspect and approve an individual proposal.

Each demo invocation creates fresh durable state in a unique subdirectory. Output defaults to `artifacts/sandbox-demo.json`; use `--output` to preserve multiple reports.

## Use the real local model

With Ollama running and `qwen3:8b` installed:

```bash
uv sync --locked --extra agent
uv run --locked --extra agent incident-lab sandbox demo --provider ollama --model qwen3:8b --approve --output artifacts/live-qwen.json
```

The model receives only read-only evidence tools. Proposal creation and approval happen in the operator workflow after the investigation. A failed or abstained investigation cannot be used by this command to propose recovery.

## Manual workflow

In terminal A, keep the server running:

```bash
python3 -m incident_lab sandbox serve --state-dir artifacts/manual-sandbox --port 8765
```

In terminal B, create the failure and inspect it:

```bash
python3 -m incident_lab sandbox probe
python3 -m incident_lab sandbox inject --state-dir artifacts/manual-sandbox --fault invalid_configuration
python3 -m incident_lab sandbox probe
python3 -m incident_lab investigate-live --output artifacts/live-investigation.json
python3 -m incident_lab sandbox propose --state-dir artifacts/manual-sandbox --investigation artifacts/live-investigation.json
```

The second probe intentionally exits 1 because it observes HTTP 503 responses. Run these commands separately rather than chaining the failing probe with `&&`. The default investigator is the rules baseline. For a model investigation, add `--provider ollama --model qwen3:8b` to `investigate-live`.

Inspect the proposal's `parameters` and `fingerprint`. Replace `PROPOSAL_ID` below with the printed ID:

```bash
python3 -m incident_lab sandbox approve --state-dir artifacts/manual-sandbox --proposal PROPOSAL_ID --ttl 60
python3 -m incident_lab sandbox execute --state-dir artifacts/manual-sandbox --proposal PROPOSAL_ID
python3 -m incident_lab sandbox probe
python3 -m incident_lab sandbox audit
```

The server returns an approval error if execution is attempted before approval. A changed revision, expired snapshot/approval, or modified parameter set also blocks execution. To inspect a different server port, pass the same `--url http://127.0.0.1:PORT` to all client commands.

Stop terminal A with Ctrl-C. Restarting with the same state directory preserves service state, role tokens, proposals, execution records, and audit history. Use a new state directory for a clean experiment; starting the server is not a reset operation.

## Exercised controls

| Control | Implementation |
| --- | --- |
| Separate demo roles | Operator token for injecting faults/approving; executor token for proposing/executing |
| Model has no write capability | No action tools, role tokens, filesystem, or shell capability in its tool set |
| Exact action binding | Immutable parameters stored with a canonical SHA-256 fingerprint |
| Evidence freshness | Snapshot age at most 300 seconds for proposal, approval, and new execution |
| Approval expiration | Operator selects a TTL of 1-300 seconds |
| Concurrent-change protection | Current state revision must equal the approved expected revision |
| Idempotency | A retry with the same proposal/key returns the prior result; another key cannot reexecute it |
| Atomic mutation | SQLite `BEGIN IMMEDIATE` serializes the revision check, configuration update, and execution record |
| Durable history | SQLite stores snapshots, approvals, execution outcomes, and audit events |
| Post-action verification | The server makes three actual `/orders` requests and records their statuses |
| Tool failures | Deployment telemetry can return HTTP 503; delayed log telemetry can trigger a client timeout |

Use `--fault telemetry_outage` or `--fault slow_telemetry` with `sandbox inject` to test observation failures. Evidence snapshots stay fixed after capture; restoring a current service state does not rewrite the investigation's observations.

## Boundaries and limitations

The server binds to `127.0.0.1`; the client accepts only loopback HTTP origins, does not follow redirects, and ignores proxy environment variables. HTTP bodies and responses are bounded, and evidence payloads are checked for service, cutoff, record type, uniqueness, and snapshot revision.

Private role tokens are stored as permission-restricted files in the selected state directory. Tokens and SQLite databases are ignored by Git. Do not publish working sandbox directories. Audit events contain role names and parameter fingerprints, not credentials.

Both demo role tokens are available to the same local OS user. This is not enterprise separation of duties, TLS, external identity management, or a tamper-proof audit store. The only mutation is restoration of the sandbox's fixed known-good configuration; there is no arbitrary configuration editing, shell execution, or remote infrastructure control.

The service currently has one workload and one recoverable configuration failure. Three successful HTTP responses are a bounded recovery check, not a production SLO or proof of sustained health. Kubernetes, Bedrock, external service adapters, and production identity integration remain future work.

The local control store has no production retention, backup, or disaster-recovery policy. Use fresh state directories for experiments and retain only reports intended for review.
