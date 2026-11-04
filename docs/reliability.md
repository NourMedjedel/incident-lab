# Evidence contracts and bounded recovery

Version 0.2 adds backend evidence checks, bounded response correction, an additional challenge suite, and the [live HTTP sandbox](sandbox.md). The original version 0.1 run remains preserved with its original outcomes.

## Evidence sufficiency

The model's prose is not used as proof that a cause is supported. A hypothesis must cite fetched recent telemetry that meets a declared minimum contract:

| Cause | Minimum recognized evidence |
| --- | --- |
| Invalid configuration | An anchored configuration-validation error and a preceding configuration change within 15 minutes |
| Application regression | An anchored unhandled-exception event and a preceding application deployment within 15 minutes |
| Dependency timeout | An anchored upstream-timeout event |
| Connection-pool resource exhaustion | An anchored pool-exhaustion event plus positive capacity, busy connections at capacity, and a nonempty queue |

All three primary telemetry tools must have been attempted before any submission and successfully returned before a hypothesis. Future, stale, cross-service, duplicate, or wrongly typed evidence does not become support. Runbooks are reference material; their words cannot create diagnostic telemetry. Quoted instructions in an INFO log do not become an ERROR event.

The policy assesses all fetched telemetry, rather than only the records selected for citation. Competing supported causes require abstention, so the model cannot avoid conflict checks by citing only one side. A hypothesis must cite a complete corroborating evidence group for its selected cause.

Once the fixed snapshot's primary tools have all been attempted and evidence is insufficient, conflicting, or unavailable, the controller offers only `submit_investigation` with an abstention schema. Repeatedly retrieving the same snapshot cannot add primary facts. This restriction and its reason are recorded in model events. The backend still validates the returned submission; it does not fabricate a successful model response.

A verified sandbox configuration recovery records a resolution event. Older configuration errors cannot support a new configuration diagnosis after that observed recovery.

This policy is intentionally conservative and format-specific. It is a minimum evidence contract, not a universal semantic verifier or causal proof. Unrecognized event formats and resource types may require escalation. The four-label vocabulary does not cover arbitrary production incidents.

## Invalid-response recovery

Text-only answers receive corrective feedback requesting a structured submission. Rejected schemas and evidence-policy violations also receive tool feedback. Default budgets allow at most two corrective responses, six total model attempts, and eight evidence-tool calls. Repair attempts consume the model budget; they do not create unbounded retries.

Invalid IDs, duplicate tool-call IDs, malformed message structures, provider failures, and exhausted budgets remain explicit failures where safe continuation is unavailable. A backend rejection is not silently graded as a successful model abstention. Failed investigations remain in the score and cannot initiate the sandbox recovery workflow.

Traces record prompt/policy versions, model events, repair usage, validation errors, evidence source, and final stop reason. The initial fixture benchmark and backend-guarded investigator are different versions; results must identify both rather than silently replacing the old score.

## Additional challenge cases

The `challenge` suite adds twelve cases covering missing changes, changes after symptoms, old errors, invalid capacity metrics, corroborated saturation, misleading runbooks/log text, competing causes, and telemetry outages. These cases were added before changing the policy implementation, but the same project author knew and edited both. They are not independently authored, held out, or independent evidence of generalization.

```bash
python3 -m incident_lab list --suite challenge
python3 -m incident_lab evaluate --suite challenge
uv run --locked --extra agent incident-lab compare --provider ollama --model qwen3:8b --suite challenge --output artifacts/challenge-comparison.json --report artifacts/challenge-comparison.md
```

The unchanged rules baseline matches expected behavior on 10/12 additional cases. New agent results are recorded separately. Existing version 0.1 predictions can still be regraded using their original fixture hashes.

For an independent evaluation, ask an external author to define new observations, expected answers, and abstention rubrics without using them to tune the implementation. Preserve provenance and hashes, keep labels out of tool responses, and report slices and execution failures. That review remains outstanding; the [independent-contribution protocol](independent-evaluation.md) defines freezing, attribution, review, and reporting requirements.

## Production grounding

The failure-mode choices are informed by public SRE guidance and an operator-written incident analysis:

- Google's [Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/) explains how retries can amplify overload and why diagnosis should precede indiscriminate restarts. This motivates bounded attempts and explicit observation failure.
- Cloudflare's [July 2, 2019 incident analysis](https://blog.cloudflare.com/details-of-the-cloudflare-outage-on-july-2-2019/) describes a deployed rule exhausting CPU and shortcomings in rollout practice. This motivates distinguishing change correlation from proof and gating recovery with explicit operator control.

The sandbox and case records are original synthetic material. They do not reproduce those organizations' internal logs or establish equivalent scale or causes. The production-style controls demonstrated here are actual HTTP failure observation, coherent evidence snapshots, expiring approval, revision checks, durable idempotency, and post-action HTTP verification.
