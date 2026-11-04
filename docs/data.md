# Data provenance and fixture contract

All observations, logs, metrics, deployment events, runbooks, and expected labels are hand-authored synthetic examples for a fictional `orders-api`. No client data, employer source code, production logs, or external dataset is included. Project code and these fixtures use the repository's MIT license; third-party models and dependencies keep their own licenses.

## Files

- `incident_lab/data/incidents.json`: observations available to the investigator.
- `incident_lab/data/ground_truth.json`: evaluation labels, required evidence IDs, and relevant runbooks.
- `examples/ollama-qwen3-8b/comparison.json`: recorded model outputs and grading, with fixture hashes.
- `incident_lab/data/challenge_incidents.json` and `challenge_labels.json`: twelve additional project-authored cases in the separate `challenge` suite. The original files are unchanged.

## Incident schema

An incident contains `id`, `service`, `title`, an ISO 8601 timezone-aware `cutoff`, `records`, and an optional `unavailable_tools` list. Records contain a unique `id`, `kind`, `service`, timezone-aware `timestamp`, and nonempty `text`. Supported kinds are `log`, `metric`, `deployment`, and `runbook`.

The fixed January 2026 times are replay time, independent of the wall-clock date. The tool gateway exposes only the incident service's records at or before the cutoff. Runbook IDs follow `name@version`; the most recently timestamped visible version for each name is selected before BM25 scoring. A later runbook does not become visible merely because the program is run months later.

The model initially receives the service, alert title, and cutoff. It does not receive the fixture object or expected answer and has no filesystem/shell tool. The labels are packaged for the local evaluator, so this is an application boundary rather than an OS-level security sandbox.

## Labels and policy

Cause labels are `invalid_configuration`, `dependency_timeout`, `application_regression`, and `resource_exhaustion`. A null expected cause means evidence is insufficient to select one cause under the suite's policy. It does not mean the service has no underlying failure.

Two unresolved competing diagnostic signatures require abstention in this suite, even if one may appear more likely. Missing required telemetry also requires abstention. `INC-007` deliberately lies outside the fixed rules' signatures while remaining diagnosable from its observations.

Required evidence IDs support coverage scoring; a reference set with no items is ungraded rather than automatic support for any prediction. Citation provenance is separate from semantic correctness. Details and case slices are in [evaluation design](evaluation.md).

## Dataset limits and changes

The original eight cases were developed with the baseline and later inspected against the agent. The twelve challenge cases were authored within the same project, before revising the policy implementation; the author knew both. Neither suite is independent or held out. They do not support generalization, production accuracy, safety, or time-saving claims.

Fixture hashes make accidental changes detectable. Preserve versioned observations/labels and matching recorded examples when changing the corpus. New independently authored cases should be identified separately from examples used to tune the system.
