# Protocol for independent evaluation contributions

An independent evaluation remains outstanding. The current development and challenge suites were authored within this project and informed implementation. This protocol describes how an external contributor can provide a separately reported evaluation without turning it into another tuning set.

## Before running the investigator

1. The external author writes observations and labels without inspecting current predictions for those cases. Use synthetic or explicitly publishable material; never copy confidential service data.
2. A second reviewer checks that the expected diagnosis follows from the visible evidence, or that abstention is justified. Resolve ambiguous cases before measuring the agent.
3. Record author/reviewer attribution, creation date, source references, synthetic transformations, and any prior exposure to the implementation. Attribution does not itself establish independence.
4. Freeze both observation and label files, record SHA-256 hashes, and identify the exact policy vocabulary being tested. Keep labels outside the tool-visible records.

Use the schemas in [data provenance](data.md). Each label should state the expected cause or null, the necessary evidence IDs, relevant runbook IDs, and a short rationale. Cases outside the four supported causes should test abstention explicitly rather than silently assigning an unsupported label.

Useful slices include missing telemetry, causally ambiguous changes, conflicting diagnostic signals, old symptoms after recovery, and ordinary supported incidents. Include counterexamples: the presence of a deployment or error keyword alone should not determine the answer.

## Freeze, run, and report

Create a separately versioned suite; do not edit the original files or fold its score into the development score. The current CLI selects the two packaged suites; registering another suite requires a reviewed addition to `incident_lab.replay.SUITES` and matching evaluation labels.

Freeze the code commit, prompt/policy/controller versions, provider/model digest, budgets, and generation settings before the first inference. Run all cases, preserve every first-run trace, and count invalid submissions and exhausted budgets as failures. Report diagnoses, required abstentions, unsupported hypotheses, execution failures, repairs, and model calls separately.

Have the external reviewer inspect results against the frozen labels. Document label corrections transparently with old/new hashes and rationale. Do not discard inconvenient outcomes or silently rerun them for the headline score.

If a failure informs a code or prompt change, that case becomes development material for the revised version. Keep the original measurement, identify the change, and obtain new independently authored cases before making a fresh generalization claim.

## Contribution record

A contribution can include this compact record beside its observation and label files:

```text
Suite ID and version:
Author / reviewer:
Created / frozen at (UTC):
Independent of implementation author? Describe any overlap:
Prior exposure to prompts, policies, or predictions:
Synthetic sources and transformations:
Observation file / SHA-256:
Label file / SHA-256:
Case slices and label rationale location:
Code commit and runtime manifest for first run:
Known ambiguities or exclusions fixed before inference:
Post-run corrections, with prior hashes:
```

A completed external contribution and its provenance are required before this project can describe a suite as independently authored. This document is a contribution protocol, not a completed evaluation.
