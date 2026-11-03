# Verification status

Publication preparation: 3 November 2026. This page records completed checks and explicit gaps; it does not claim remote CI has passed before the repository is published.

## Application behavior

- The rules baseline ran all eight synthetic cases, matching expected behavior on seven.
- Real local `qwen3:8b` inference ran once per case, matching expected behavior on five; it identified all four diagnosable causes but made two unsupported diagnoses and had one protocol failure.
- Full traces and grading are preserved in [the reference artifact](../examples/ollama-qwen3-8b/comparison.json) and [failure analysis](qwen3-8b-comparison.md).
- Groq and Anthropic integrations have mock-transport verification only. No paid provider calls were used for the reference comparison.
- The scripted `agent-demo` is labeled as hand-authored and excluded from quality comparisons.

## Repository preparation checks

A temporary local Git repository and fresh clone were created from the publication candidate, excluding existing environments, caches, working traces, downloaded weights, and the parent portfolio documents. No GitHub remote was created.

| Clean locked install | Result |
| --- | --- |
| CPython 3.11.6 | 71 tests passed, 8 parameter subtests |
| CPython 3.12.9 | 71 tests passed, 8 parameter subtests |
| CPython 3.13.9 | 71 tests passed, 8 parameter subtests |
| CPython 3.14.0 | 71 tests passed, 8 parameter subtests |

Additional completed checks:

- The documented dependency-free demo and saved-score replay ran from the clean clone before installing optional packages.
- The standard-library runner completed 71 tests on Python 3.11 with 28 optional-dependency tests explicitly skipped.
- Ruff lint and format checks passed. The documentation checker validated 15 Markdown files and 36 relative file links.
- The source candidate was scanned for common API-key/private-key patterns and machine-specific paths; no matching secrets or private paths were found. This scan does not guarantee detection of every possible secret.
- Both the source distribution and wheel built successfully. Archive checks confirmed the fixture JSON, CLI, license, documentation, tests, scripts, curated examples, and required root files, excluding local environments and working artifacts.
- The wheel was installed with no dependencies into a separate Python 3.12 environment. The baseline and offline replay ran in isolated Python mode from outside the source checkout; imports resolved from the installed wheel.
- The source archive was extracted into a new directory; documentation checks and saved-score replay passed there as well.
- The MIT license, package metadata, LF checkout attributes, and locked optional dependencies are included in the candidate.

Python 3.14 emitted 13 dependency deprecation warnings from LangSmith's use of `asyncio.iscoroutinefunction`; Python 3.11-3.13 passed without those warnings. No additional model inference or paid API calls were used by this publication audit.

## Known verification gaps

- Remote GitHub Actions cannot be confirmed before the repository is created and its checks run.
- The local Docker daemon was unavailable; the Dockerfile is a documented baseline recipe, not a verified local container deployment.
- New inference is not byte-for-byte reproducible. The original artifact recorded a model ID prefix, not a complete hardware/environment manifest.
- Kubernetes, Bedrock, live enterprise integrations, and remediation actions are not implemented or verified.

## Review corrections retained

An empty reference evidence set no longer grants a speculative diagnosis full citation coverage. Valid message structures with an invalid final tool protocol are retained in new conversation traces. The original inference outcomes remain preserved; corrections were graded from saved predictions without repeating inference.
