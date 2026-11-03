# Recorded local Qwen3-8B runs

Model: `qwen3:8b` through local Ollama. Scenario: `INC-007`. Reviewed 3 November 2026.

The first local CLI output is preserved in [INC-007-first-run.json](INC-007-first-run.json). It contains synthetic incident data, tool events, and the visible conversation from actual model inference.

## Observed behavior

The model requested logs, metrics, and deployment history, then searched runbooks and submitted a `resource_exhaustion` hypothesis. The backend accepted the submission with no validation errors.

The cited log reports `CONNECTION_POOL_EXHAUSTED` with all 20 connections busy. The cited metric reports 20 busy connections out of 20, plus a queue depth of 140. The hypothesis matches the development fixture's expected diagnosis. The fixed rules baseline abstains on this case because it has no pool-exhaustion rule.

| Observation | Recorded value |
| --- | --- |
| Model requests | 3 |
| Evidence-tool calls | 4 |
| Input tokens, summed over requests | 2,931 |
| Output tokens | 238 |
| End-to-end duration | 46.383 seconds |
| Submission validation errors | 0 |

These timings describe one local run. They are not a latency distribution or a comparison with hosted inference. The trace identifies a model tag but not an immutable model digest, so this first artifact alone does not completely identify its weights.

## What still needs improvement

The query `connection pool exhausted` retrieved `upstream@1`, an upstream-timeout procedure. It does not directly address pool exhaustion. The model cited it despite its limited relevance. Checking that an ID was returned by a tool does not establish that the document supports the proposed diagnosis or next step.

The model proposed investigating load and possible pool-size or scaling changes. No remediation was executed or validated. Pool exhaustion alone does not establish whether the cause is demand, slow queries, leaked connections, or database capacity. The next iteration needs evidence that distinguishes those possibilities before recommending a specific change.

The complete eight-case result is preserved in [comparison.json](comparison.json), with fixture hashes and reviewed metrics. The model matched expected behavior on 5/8 cases, including failures on missing evidence, conflicting signals, and a telemetry outage. See [failure analysis](../../docs/qwen3-8b-comparison.md) and [offline replay instructions](../../docs/reproducibility.md). These are development observations, not broader reliability claims.
