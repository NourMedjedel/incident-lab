# Reproducibility

## What can be reproduced exactly

The rules baseline and grading of saved model predictions run without optional packages. From the repository root:

```bash
python3 -m incident_lab evaluate
python3 -m incident_lab replay examples/ollama-qwen3-8b/comparison.json
```

Expected counts:

| Report | Behavior matches | Cases | Execution failures |
| --- | --- | --- | --- |
| Rules | 7 | 8 | 0 |
| Recorded Qwen3-8B predictions | 5 | 8 | 1 |

Execution duration and generated timestamps vary. The offline replay checks observation/label file hashes before regrading and rejects incompatible data or incomplete artifacts. It recomputes metrics from the saved predictions, not from their saved summary. Historical model-request counts and tokens remain labeled as historical; replay makes no model calls.

The curated artifact is [comparison.json](../examples/ollama-qwen3-8b/comparison.json). Its `provenance` records fixture hashes, the original output hash, the installed model ID prefix, and that scores were reviewed without new inference. The original workstation's ignored `artifacts/` folder is not needed. `.gitattributes` keeps text line endings at LF so Git checkout settings do not change the fixture bytes on Windows.

## Locked setup

Requires Python 3.11+. The project is tested/configured across Python 3.11-3.14; see [verification](verification.md) for completed local checks. uv 0.8.14 is used by CI, and `uv.lock` records dependency versions.

```bash
uv sync --locked --extra dev --extra agent
uv run --locked --extra dev --extra agent pytest
```

`--locked` refuses to silently resolve a changed dependency graph. Runtime-only baseline use has no dependencies. The `agent` extra adds LangGraph, HTTP support, and the Anthropic SDK; installing these libraries makes no model calls. The `dev` extra adds pytest and Ruff.

uv may download a suitable Python interpreter if none is available. Use `uv sync --locked --python 3.12 --extra agent` to select an interpreter explicitly. Network access is required to install uncached packages and to download model weights.

The lockfile controls application dependencies; the setuptools build backend is specified separately in `pyproject.toml`. Artifact bytes, platform wheels, and live model output are not promised to be identical across machines.

## Repeat inference, rather than replay predictions

Install the agent extra, start Ollama, and download `qwen3:8b` as described in [provider setup](free-prototype.md). Then:

```bash
uv run --locked --extra agent incident-lab compare --provider ollama --model qwen3:8b --output artifacts/new-comparison.json --report artifacts/new-comparison.md
```

The adapter uses non-streaming chat, `think=false`, temperature 0, an 8,192-token context option, and a 1,024-token generation limit. Default investigator budgets are six model attempts and eight evidence-tool calls per case. These parameters remain visible in source and the output records the model name, prompt version, limits, usage, tool events, visible conversation, and stop reason.

The reference run used Ollama model ID prefix `500a1f067a9f`. The first artifact did not capture the full immutable digest or detailed hardware, and model tags can move. Record `ollama list`, Ollama version, machine details, and any changed settings alongside a new experiment. Temperature 0 and identical prompts do not guarantee identical model outputs or timings.

The first eight-case run used 24 model requests and took about 159 seconds in total. This is not a time budget for another machine. The host model adapters use 30-second request timeouts; local Ollama uses 120 seconds per request. The six-call limit bounds attempts, not total wall-clock time to exactly six times that value.

## Reports and exit codes

| Command | Meaning of success / failure |
| --- | --- |
| `demo` / `evaluate` | 0 means the baseline ran; a missed diagnosis is still reported |
| `agent` | 0 means a validated hypothesis or abstention; 1 means execution failed |
| `compare` | Writes all case results; exits 1 if any investigation failed |
| `replay` | 0 means saved predictions were regraded, even when they preserve a model failure |
| Configuration or invalid replay artifact | Exit 2 with an actionable error |

Output paths can be overridden with `--output` and, where applicable, `--report`. Re-running a command replaces files at those paths; use separate names for experiments you intend to preserve. `artifacts/` is ignored by Git. Curated reference results in `examples/` are intentionally versioned.

## Package and container paths

```bash
uv build
python3 scripts/check_distributions.py
```

The wheel includes the Python package, license, and fixture JSON needed by the CLI. The source distribution additionally includes documentation, tests, scripts, and curated examples. The wheel can run the baseline from another working directory; the replay command needs an explicit path to a saved artifact from the source checkout.

The Dockerfile packages the dependency-free baseline only:

```bash
docker build -t incident-lab .
docker run --rm incident-lab demo --scenario INC-001
```

Docker and remote GitHub Actions status are recorded in [verification](verification.md). They are not prerequisites for the verified Python quickstart.
