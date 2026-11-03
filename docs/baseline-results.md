# Incident Lab: baseline evaluation

Small synthetic development suite; not a held-out or production benchmark.

Engine: `rules-v1` · Fixtures: `1` · Python: `3.14.0`

Behavior matches: **7/8**. Answered: **3/8**. LLM calls: **0**.

A correct abstention counts as a behavior match. Coverage and diagnostic recall must be considered alongside accuracy on answered cases.

| Case | Expected | Predicted | Match |
| --- | --- | --- | --- |
| INC-001 | invalid_configuration | invalid_configuration | yes |
| INC-002 | dependency_timeout | dependency_timeout | yes |
| INC-003 | application_regression | application_regression | yes |
| INC-004 | abstain | abstain | yes |
| INC-005 | abstain | abstain | yes |
| INC-006 | abstain | abstain | yes |
| INC-007 | resource_exhaustion | abstain | no |
| INC-008 | abstain | abstain | yes |

The fixtures were written with the baseline and are development examples, not independent evidence of generalization. Pool exhaustion is a deliberately unsupported case: it should expose the baseline's limited coverage.
