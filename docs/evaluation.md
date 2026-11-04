# Evaluation design

## Data and boundaries

`incident_lab/data/incidents.json` contains hand-authored synthetic observations for a fictional `orders-api`. No customer logs, employer code, or external dataset is included.

All incident timestamps are fixed in January 2026. They represent replay time, not the date a command runs. The investigator can see only records for its incident service at or before the cutoff. Runbook IDs use `name@version`; retrieval selects the most recently timestamped visible version for each name before scoring.

`ground_truth.json` is read only by the evaluator and is not passed to the investigator. Each prediction is scored after it returns. Labels specify the expected answer from the visible evidence, required supporting evidence IDs, and relevant runbook versions. A null expected cause means abstention is required. It does not imply that the simulated failure has no underlying cause.

| Case | Behavior under test |
| --- | --- |
| INC-001 | Invalid configuration after a change; unrelated service evidence filtered out |
| INC-002 | Dependency timeout |
| INC-003 | Exception after an application release |
| INC-004 | Insufficient evidence |
| INC-005 | Future deployment and logs must not leak into the diagnosis |
| INC-006 | Deployment tool unavailable |
| INC-007 | Pool exhaustion outside the baseline's supported signatures |
| INC-008 | Conflicting application and upstream signals |

## Metrics

- **Behavior matches:** predicted cause equals the expected cause, including null/null abstentions.
- **Incorrect hypotheses:** non-null diagnostic answers that do not match the expected answer. Blocking a diagnosis may reduce this count while still leaving explicit execution failures.
- **Answer coverage:** non-null predictions divided by all cases. High answered-case accuracy can coexist with low coverage.
- **Diagnostic recall:** correct diagnoses divided by cases with a non-null expected cause.
- **Accuracy when answered:** correct diagnoses divided by non-null predictions.
- **Appropriate abstention:** abstentions divided by cases where the expected answer is abstention.
- **Required evidence coverage:** evaluated answers citing all required evidence IDs divided by answered cases with a nonempty reference evidence set. Report the denominator as `required_evidence_evaluated_count`. No reference evidence means ungraded, not automatic support for a diagnosis. This checks label coverage, not semantic faithfulness or causal validity.
- **Runbook Recall@2:** fraction of labeled relevant runbooks among the first two unique fetched runbooks. For the baseline this is its single query's top two; the agent may issue several queries, so this metric describes its first two returned documents rather than an aggregate top-k over unlimited searches. Cases without relevant labels are excluded from this average.

Per-case results expose slices and tool failures. The rules baseline makes no LLM calls and has zero LLM cost. The agent records observed provider token usage; incomplete usage or missing price rates leaves cost unknown. Failed executions never count as successful abstentions.

`evaluate` returns a report even when a prediction is wrong. Its exit code indicates successful execution, not quality acceptance. Regression behavior is checked separately by the tests. Future release gates need explicit slice-level acceptance thresholds and a held-out dataset.

## Interpretation and next experiments

The current suite is a development aid designed alongside the rules. It does not support claims about generalization, client time savings, production incident resolution, or LLM safety. Temporal correlation only supports a hypothesis.

Before comparing an agent, preserve this baseline and the incident-time view. Author additional scenarios without tailoring them to the implementation; separate development and held-out incident families, not near-duplicate rows. Expand the workload enough to report uncertainty and error slices meaningfully. Do not present the eight-case percentage as hiring evidence of model quality.

The injection test proves only that a rule engine does not execute retrieved instructions. An LLM agent requires a separate adversarial evaluation and backend authorization checks.

Version 0.2 evaluates the combined model/controller/policy workflow. Its backend can require escalation and expose only an abstention schema after observing insufficient or competing signals. Improvements therefore measure the guarded application, not an independently improved foundation model. Schema/evidence rejection is not itself a successful abstention; the model must submit a valid result within budget, or the run remains failed.

Use `--suite challenge` to evaluate twelve additional project-authored cases. These are separate from the original eight, but are not independent or held out. Suite-specific hashes are saved in comparisons and checked on replay. Original v0.1 artifacts remain compatible.

## Live comparison

`compare` uses a real model provider to evaluate the same incident-time fixture view, then writes a baseline/agent report and full traces. The recorded [local Qwen comparison](qwen3-8b-comparison.md) matched expected behavior on 5/8 cases; the baseline matched 7/8. The guarded v0.2 workflow matched 8/8 original and 11/12 challenge cases in [a separately recorded experiment](reliability-results.md). Hosted providers have not been evaluated with actual model requests. The scripted graph example is refused by this runner. The `replay` command regrades saved predictions without inference; see [reproducibility](reproducibility.md).
