# Contributing

Use Python 3.11-3.14 and uv. uv 0.8.14 is the bootstrap version used by CI; the checked-in lockfile pins optional dependencies.

```bash
uv sync --locked --extra dev --extra agent
uv run --locked --extra dev ruff check .
uv run --locked --extra dev ruff format --check .
uv run --locked --extra dev --extra agent pytest
python3 scripts/check_docs.py
python3 -m incident_lab replay examples/ollama-qwen3-8b/comparison.json
```

These checks do not need API keys or a running Ollama server. If changing code style, run `uv run --locked --extra dev ruff format .` and `uv run --locked --extra dev ruff check --fix .`.

For packaging changes, also run `uv build` and `python3 scripts/check_distributions.py`. The archive check verifies fixture resources, the license, documentation, and curated replay inputs without including local environments or working traces.

## Useful changes

Prioritize evidence sufficiency, abstention, invalid-response recovery, and retrieval evaluation. Describe a failure and its observable behavior before proposing another integration. A narrowly scoped fix with a reproducible case is easier to assess than an unmeasured framework addition.

Keep the rules baseline independently runnable. Optional providers should preserve tool-result pairing, obey the gateway, report observed usage, and expose failures without falling back to another endpoint. Use mocked transports for default tests; actual model runs must be explicit and outside CI.

## Data and result changes

The existing eight cases are development fixtures, not held-out tests. Explain new labels and identify which changes were informed by existing model failures. Keep independently authored evaluation cases separate from cases used to tune prompts or rules. Follow the [independent-evaluation contribution protocol](docs/independent-evaluation.md); no independent suite has been completed yet.

Fixture hashes are part of the recorded comparison contract. Changing the canonical corpus invalidates replay of the checked-in historical artifact on that checkout. Preserve historical data/version provenance and update example compatibility intentionally when versioning a dataset. Do not silently replace results with a more favorable run.

## Propose a change

The README animation is an illustrated workflow. Regenerate it with `uv run --script scripts/render_workflow.py`; Pillow is isolated to that rendering command and is not an application dependency. Commit both the GIF and its static PNG alongside any renderer change.

Open an issue or pull request with the problem, proposed behavior, relevant traces, and checks run. Include only synthetic or publishable data. Keep credentials, local environments, downloaded weights, and generated working traces out of the commit; `artifacts/` is ignored. The curated examples are intentionally included.

Model requests are not part of the default test suite, and a successful API response is not evidence of improved quality. Compare against the baseline and report failure slices as well as overall counts.
