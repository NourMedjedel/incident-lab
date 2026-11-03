# Incident Lab: baseline vs agent

One local inference run per synthetic development case; not held-out or production evidence.

Provider: `ollama` · Model: `qwen3:8b`

| Measure | Rules | Agent |
| --- | --- | --- |
| behavior_correct_count | 7 | 5 |
| answered_count | 3 | 6 |
| diagnostic_recall | 0.75 | 1.0 |
| failed_count | 0 | 1 |
| llm_calls | 0 | 24 |
| input_tokens | 0 | 23684 |
| output_tokens | 0 | 1873 |
| estimated_llm_cost_usd | 0 | unknown |

Execution failures count as incorrect, including on expected-abstention cases. Unknown cost is not zero. Any provided rates yield an estimate, not an invoice. Full JSON includes per-case outcomes and agent traces.

## Per-case review

| Case | Expected | Rules | Qwen | Outcome |
| --- | --- | --- | --- | --- |
| INC-001 | invalid_configuration | invalid_configuration | invalid_configuration | match |
| INC-002 | dependency_timeout | dependency_timeout | dependency_timeout | match |
| INC-003 | application_regression | application_regression | application_regression | match |
| INC-004 | abstain | abstain | invalid_configuration | miss |
| INC-005 | abstain | abstain | abstain | match |
| INC-006 | abstain | abstain | execution failed | miss |
| INC-007 | resource_exhaustion | abstain | resource_exhaustion | match |
| INC-008 | abstain | abstain | application_regression | miss |

## Interpretation

The agent identified all four diagnosable fixture causes, but incorrectly diagnosed two cases requiring abstention. It also failed to submit a valid abstention after a telemetry-tool outage. The rule baseline therefore matched expected behavior more often overall (7/8 versus 5/8). The model adds coverage on pool exhaustion while weakening abstention reliability in this development suite.

There were 24 model requests in total. Median per-case duration was 18.1 seconds, with a 13.7–26.2 second range; total investigation time was 159.1 seconds. These are eight single observations on one machine, not repeated performance measurements.

The model was local qwen3:8b, installed ID prefix 500a1f067a9f. There were no hosted model API requests. The cost field remains unknown because the application did not estimate local hardware or energy costs.

## Failure analysis

- INC-004: the explanation acknowledges an unexplained HTTP 500 increase, yet the cause field selects invalid_configuration without supporting configuration evidence.
- INC-006: the backend correctly rejected a hypothesis when deployment telemetry was unavailable. The model then failed the required tool-call protocol rather than submitting an abstention. The original artifact did not retain the final non-tool reply; that observability gap is now fixed for future runs.
- INC-008: the explanation recognizes both application and dependency signals, but the cause field selects application_regression. Under this suite’s explicit policy, unresolved competing signals require abstention.
- INC-007: the diagnosis is supported by telemetry, but its retrieved upstream-timeout runbook is only loosely relevant. Citation provenance alone does not establish semantic support.

## Review changes and reproduction

After inspecting this run, the evaluator was corrected so an empty reference-evidence set does not automatically credit a speculative diagnosis. Saved predictions were regraded without making additional model requests; the 5/8 and 7/8 behavior scores are unchanged. Full traces and fixture hashes are preserved in [the example artifact](../examples/ollama-qwen3-8b/comparison.json).

Reproduce from the repository root:

```bash
uv run --locked --extra agent incident-lab compare --provider ollama --model qwen3:8b
```

For a fresh checkout without a model, reproduce the recorded scores from the checked-in artifact:

```bash
python3 -m incident_lab replay examples/ollama-qwen3-8b/comparison.json
```

The artifact contains all recorded predictions; no ignored working files are needed. Replay verifies fixture hashes and performs no inference. New inference runs may differ. This is a synthetic development suite authored alongside the baseline, not a held-out test or evidence of production readiness.

## Next engineering work

Prioritize a clearer evidence-sufficiency policy, recovery from invalid final responses, and evaluation of abstention before introducing remediation actions. Preserve this run as the reference and evaluate any changes on additional independently authored cases rather than only tuning to these eight.
