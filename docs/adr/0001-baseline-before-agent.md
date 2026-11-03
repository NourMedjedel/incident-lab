# ADR 0001: establish an inspectable baseline before agent orchestration

Status: accepted for milestone one.

## Context

The project must eventually demonstrate whether an agent adds useful diagnostic capability at an acceptable cost. Starting with a model makes it easy to confuse plausible narration, leaked answers, and actual improvements.

## Decision

Implement a dependency-free rules investigator over timestamped fixtures. Expose evidence through four constrained tools. Keep expected answers in a separate evaluation resource and record every tool call. Preserve unsupported and ambiguous cases in the results.

Use keyword retrieval first. It is a measurable baseline, easy to inspect, and requires neither an embedding service nor external credentials. Its runbooks are reference material for this milestone; they do not generate the diagnosis.

## Consequences

Anyone with Python 3.11+ can reproduce the first demonstration. It costs no model tokens and has an explicit coverage gap for the future agent to address.

This baseline is not an agent or an enterprise integration. It cannot establish real-time service health, enforce production identity policies, or validate operational remediations. Introduce the LLM and live adapters as separate experiments, using the same evidence and evaluation contracts.

Backend authorization for supervised actions will be a later decision. Prompt instructions are not access control.
