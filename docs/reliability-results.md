# Reliability experiment: guarded Qwen3-8B

Version 0.2 changes the application policy and controller, not the model weights. It adds minimum evidence contracts, required abstention on insufficient/conflicting/unavailable primary evidence, and bounded correction of invalid submissions. The original version 0.1 results remain preserved.

This is a single recorded run per project-authored case using local Ollama `qwen3:8b`. Both suites are development material known to the implementation author. Neither is independently authored or held out; these results do not estimate production accuracy.

## Unchanged original eight cases

| Measure | Rules | Qwen v0.1 | Guarded Qwen v0.2 |
| --- | --- | --- | --- |
| Expected behavior matches | 7/8 | 5/8 | 8/8 |
| Correct diagnoses | 3/4 | 4/4 | 4/4 |
| Required abstentions completed correctly | 4/4 | 1/4 | 4/4 |
| Incorrect hypotheses accepted | 0 | 2 | 0 |
| Execution failures | 0 | 1 | 0 |
| Model calls | 0 | 24 | 22 |

Two cases exercised correction: `INC-004` initially cited an unseen runbook, and `INC-006` attempted unseen citations and an invalid schema after deployment telemetry failed. Both eventually returned validated abstentions within their budgets. The trace preserves those rejections rather than hiding them behind the final score.

The controller now restricts admissible operations after primary evidence requires escalation. Improved abstention is therefore partly enforced by application logic. This does not show that Qwen independently learned a more reliable diagnostic policy.

Retrieval remains weak: the guarded run's mean runbook recall at two was approximately 0.143 on eligible original cases. The agent often submitted without retrieving a runbook; the abstention controller also prevents unnecessary retrieval after escalation is required. This experiment improves evidence-bound decisions and protocol completion; it does not establish improved RAG quality.

## Additional twelve challenge cases

| Measure | Rules | Guarded Qwen v0.2 |
| --- | --- | --- |
| Expected behavior matches | 10/12 | 11/12 |
| Correct diagnoses | 2/3 | 2/3 |
| Required abstentions completed correctly | 8/9 | 9/9 |
| Incorrect hypotheses accepted | 1 | 0 |
| Execution failures | 0 | 0 |
| Model calls | 0 | 33 |

`CH-010` remains incorrect: the model selected a configuration cause from old distractor evidence, the backend rejected it, and the model then abstained despite a supported application-regression signal. The guard prevented an unsupported diagnosis but did not recover the correct diagnosis. This is a coverage limitation, not a correct abstention.

Five challenge cases used one corrective response each. The run completed all twelve cases without silently converting a failed execution into an abstention. No repeated-run reliability or statistical uncertainty was measured.

## Actual local HTTP experiment

The same local model investigated a running SQLite-backed orders service through HTTP evidence tools. Real requests returned `[200, 200, 200]` before injection and `[503, 503, 503]` after an invalid configuration change. A parameter-bound proposal was explicitly approved with the demo flag; execution restored the fixed known-good configuration, and the server recorded three successful HTTP verification requests. Three additional requests also returned 200.

The saved [live demo and audit](../examples/reliability-v2/live-demo.json) records the read-only investigation, exact proposal, expiring approval, execution, and verification. The model has no action tools or role tokens. The `--approve` flag automates the operator step in this isolated demo; it is not a separate person's review or a production deployment.

Run the dependency-free [sandbox workflow](sandbox.md) to reproduce the failure and recovery without any account or paid inference.

## Reproduction

The original v0.1 traces and [failure analysis](qwen3-8b-comparison.md) remain available. Current full conversations, validation errors, tool traces, settings, and fixture hashes are preserved in separate artifacts:

- [Original eight cases, guarded investigator](../examples/reliability-v2/development.json)
- [Twelve challenge cases](../examples/reliability-v2/challenge.json)
- [Runtime manifest and complete model digest](../examples/reliability-v2/runtime.json)

Inference used code commit `fe09410` on Python 3.14.0 / macOS arm64, local `qwen3:8b`, temperature 0, `think=false`, an 8,192-token context, and a 1,024-token output limit. The runtime manifest preserves source hashes and the full prompt. A subsequent resource-cleanup fix explicitly closes business SQLite connections; it does not change the agent, policy, controller, fixtures, or provider. The measurements have not been relabeled as a new inference run after that fix.

Regrade the saved outputs using only Python 3.11+:

```bash
python3 -m incident_lab replay examples/reliability-v2/development.json --output artifacts/replay-v2-development.json --report artifacts/replay-v2-development.md
python3 -m incident_lab replay examples/reliability-v2/challenge.json --output artifacts/replay-v2-challenge.json --report artifacts/replay-v2-challenge.md
```

Expect agent behavior matches of **8/8** and **11/12**, respectively, with zero recorded execution failures. Replay checks fixture hashes and recomputes scores without model requests. For fresh inference, use the [locked setup](reproducibility.md) and run `compare` separately for each suite with distinct output paths. Model output and timings can vary even with the same settings.

Independent evaluation remains outstanding; follow the [external-contribution protocol](independent-evaluation.md). Kubernetes, Bedrock, sustained-load testing, enterprise identity, and external production operations remain future work.
