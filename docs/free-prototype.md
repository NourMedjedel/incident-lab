# Model providers and setup

Provider plans and catalogues change. Hosted free-tier details below were checked on 3 November 2026; verify availability in your account. The dependency-free baseline and offline [saved-score replay](reproducibility.md) need no provider account.

## Choose a mode

| Mode | Account / key | Model execution | Verification |
| --- | --- | --- | --- |
| Rules baseline | None | None | Tested locally |
| `agent-demo` | None | Hand-authored responses through the graph | Tested locally; not inference |
| Ollama | None for downloaded local models | Real local inference | Qwen3-8B development comparison recorded |
| Groq | Groq key; Free plan for no-cost hosted use | Hosted inference | Mock-transport tests only |
| Anthropic | Anthropic key and an account-accessible model | Hosted inference, normally paid | Mock-transport tests only |

LangGraph is the local orchestration library. This project does not require a LangGraph account, LangSmith subscription, or cloud deployment. [LangGraph documentation](https://docs.langchain.com/oss/python/langgraph/overview).

## Local Ollama: recommended verified path

1. Install [Ollama](https://ollama.com/download).
2. Start its desktop application. Alternatively, run `ollama serve` in a separate terminal if a server is not already running. Do not start a second server on the same port.
3. From the project root, install the optional agent dependencies and download the model:

```bash
uv sync --locked --extra agent
ollama pull qwen3:8b
ollama list
uv run --locked --extra agent incident-lab agent --provider ollama --model qwen3:8b --scenario INC-007
```

The Qwen3-8B quantized artifact is about 5.2 GB and needs additional working memory. Weights have an Apache 2.0 license; they are not bundled with this repository. Model size on disk is not a RAM requirement. [Ollama listing](https://ollama.com/library/qwen3:8b), [publisher model card](https://huggingface.co/Qwen/Qwen3-8B).

The adapter uses `127.0.0.1:11434`, ignores proxy environment variables, rejects cloud-tagged names, and has no hosted fallback. Select an actual downloaded model. Server aliases and Ollama's cloud configuration are outside the adapter. For strict local operation, set `OLLAMA_NO_CLOUD=1` on the server and restart it as described in the [Ollama FAQ](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features).

Try one case before running the suite:

```bash
uv run --locked --extra agent incident-lab compare --provider ollama --model qwen3:8b
```

Local inference has no provider API fee. Hardware and electricity are not estimated by this application. New results may differ from the [reference comparison](qwen3-8b-comparison.md).

## Groq Free plan

Create an account in the [Groq console](https://console.groq.com/), keep it on the Free plan, and create an API key. Configure `GROQ_API_KEY` locally. A Developer upgrade is a paid usage plan requiring a payment method. [Billing documentation](https://console.groq.com/docs/billing-faqs).

Select a currently available tool-calling model using `GROQ_MODEL` or `--model`. At review time, `qwen/qwen3.8-27b` was listed in the free-plan quotas and tool-support table. Confirm it is available in your account. [Rate limits](https://console.groq.com/docs/rate-limits), [tool support](https://console.groq.com/docs/tool-use/overview).

```bash
export GROQ_MODEL='qwen/qwen3.8-27b'
uv run --locked --extra agent incident-lab agent --provider groq --scenario INC-007
```

The example assumes the key is already present in the environment. The CLI does not load `.env` files. `--provider` defaults to `groq`, but explicit selection is clearer in scripts. Do not commit your credentials or include them in issue reports.

The application cannot inspect or change the account's billing tier. It stops on HTTP 429 and never switches providers or upgrades a plan. Token-per-minute quotas can interrupt a multi-turn investigation or an eight-case comparison; start with a single case and wait before retrying when limited.

## Anthropic, optional

Configure `ANTHROPIC_API_KEY` locally and choose a model accessible to the account:

```bash
export ANTHROPIC_MODEL='your-available-model-id'
uv run --locked --extra agent incident-lab agent --provider anthropic --scenario INC-007
```

This is a hosted provider and is not the no-cost local route. Automatic SDK retries are disabled. No live Anthropic test was performed for the reference results.

## Configuration reference

| Variable | Purpose |
| --- | --- |
| `OLLAMA_MODEL` | Local model name if `--model` is omitted |
| `GROQ_API_KEY` / `GROQ_MODEL` | Groq credentials and model name |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | Anthropic credentials and model name |

`--model` overrides the selected provider's model environment variable. `--max-model-calls` accepts 1-20 and defaults to 6; `--max-tool-calls` accepts 1-32 and defaults to 8. Hosted comparisons send synthetic fixture metadata and fetched synthetic evidence to the selected provider. The local adapter does not send API credentials.

Cost remains unknown without both `--input-rate` and `--output-rate` in USD per million tokens. Supplied rates produce an estimate, not an invoice. Unknown or cached usage prevents that estimate. For local Ollama, the cost field does not estimate your machine's energy/hardware cost.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `No module named incident_lab` | Run from the checkout root or install the package; use `uv run --locked ...` for its entry point |
| Missing optional dependency | Run `uv sync --locked --extra agent`; keep `--extra agent` on agent commands |
| Ollama connection failed | Start the server; check `ollama list` and port 11434 |
| Ollama HTTP 404 | Check `ollama list`; download the exact model tag used by `--model` |
| Ollama HTTP 400 | Select a model supporting native tool calling and the requested options |
| No tool calls / `invalid_tool_protocol` | Inspect the saved visible response; the agent requires a structured submission |
| Tool budget / model budget exhausted | Inspect the trace before increasing budgets; another call is not automatically useful |
| Hosted HTTP 401/403 | Check the local key, model permissions, and account access |
| Hosted HTTP 429 | Wait for quota reset; the application does not retry automatically |
| Changed model or dependency versions | Preserve a new artifact; do not overwrite the reference result |

## Other free-tier options

Google's Gemini Developer API advertises free access to selected models within limited quotas. Free-tier content may be used to improve Google's products under its terms. A Gemini adapter is not implemented here. [Current pricing](https://ai.google.dev/gemini-api/docs/pricing).
