# Verification status

Local reliability milestone checked on 4 November 2026. These are completed local checks; remote CI and Docker status are stated separately.

## Application behavior

- A real local Ollama `qwen3:8b` run completed the guarded original eight-case suite with 8/8 behavior matches, four correct diagnoses, four required abstentions, and zero execution failures.
- A separate real-model run completed twelve project-authored challenge cases with 11/12 matches, two of three diagnoses, all nine required abstentions, and zero execution failures. One supported application diagnosis was missed through unnecessary abstention.
- No incorrect hypotheses were accepted in either recorded guarded run. These small development suites are not independently authored or held out.
- A real HTTP sandbox experiment with Qwen observed healthy requests, an injected configuration failure, an explicitly approved fixed restoration, and successful HTTP verification: 200 → 503 → 200.
- Full conversations, rejections, model/source hashes, and audit records are preserved in [the current experiment](reliability-results.md). Offline replay reproduced both current scores and the original v0.1 score without model calls.
- Groq and Anthropic integrations remain mock-transport tested. No paid model requests were used.

## Local checks

| Locked install | Result |
| --- | --- |
| CPython 3.11.6 | 106 tests passed, 22 parameter subtests |
| CPython 3.12.9 | 106 tests passed, 22 parameter subtests |
| CPython 3.13.9 | 106 tests passed, 22 parameter subtests |
| CPython 3.14.0 | 106 tests passed, 22 parameter subtests |

Python 3.11–3.13 checks used separate temporary source copies and fresh locked environments. Python 3.14 ran in the project environment. The standard-library unittest runner also completed all 106 discovered tests on Python 3.14, with 34 optional-dependency tests explicitly skipped. Local HTTP tests require permission to bind loopback sockets.

The tests exercise evidence contracts, response repair budgets, actual HTTP failures/timeouts, service/time/snapshot boundaries, unauthorized execution, approval expiry, stale evidence/revisions, parameter changes, concurrent exactly-once mutation, idempotent retries, and restart persistence. Business SQLite connections are explicitly closed; the dependency-free run completed without resource warnings after that correction.

Ruff lint/format and documentation checks passed for 20 Markdown files and 58 relative links. A scan of the 65-file publication candidate found no sandbox token values, common private-key/API-key patterns, or workstation paths; this does not guarantee detection of every possible secret. Curated model artifacts are stored separately from ignored working state, tokens, and databases.

Both the v0.2 source archive and wheel built successfully and passed archive-content checks. The wheel was installed without dependencies in a fresh Python 3.12 environment outside the checkout. Isolated-mode baseline, challenge evaluation, all three saved-score replays, and the actual HTTP recovery demo passed with imports resolving from the installed wheel. Documentation checks and challenge replay also passed from the extracted source archive.

Python 3.14 emitted 13 dependency deprecation warnings from LangSmith's use of `asyncio.iscoroutinefunction` when optional agent libraries were installed. Python 3.11–3.13 completed without those warnings.

## Historical v0.1 verification

The initial publication candidate passed 71 tests and 8 parameter subtests across Python 3.11–3.14. Clean-clone baseline/replay, wheel installation outside the checkout, source-archive workflows, lint, documentation links, and distribution-content checks passed. The [original model experiment](qwen3-8b-comparison.md) remains preserved at 5/8 matches, including two unsupported diagnoses and one protocol failure. Those outcomes were not overwritten by v0.2.

## Known verification gaps

- Remote GitHub Actions results for this feature branch have not been verified here.
- The local Docker daemon was unavailable; container execution remains a remote CI check, not a verified local deployment.
- New inference is not byte-for-byte reproducible; no repeated-run accuracy or latency distribution was measured.
- External independent evaluation, sustained-load/soak testing, enterprise IAM, and external service integration remain outstanding.
- The sandbox exercises one workload and one approved recovery action on one machine. Kubernetes, Bedrock, and production operations are future work.
