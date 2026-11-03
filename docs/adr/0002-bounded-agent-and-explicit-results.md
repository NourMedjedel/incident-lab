# ADR 0002: bounded agent with backend-validated submissions

Status: accepted. Local Ollama inference has since been verified; hosted-provider verification remains mock-based.

## Context

The project needs to compare model-driven investigation with the fixed rules. Free-text responses are difficult to grade and may invent citations, conflate execution failure with abstention, or obscure model usage.

## Decision

Use LangGraph to alternate model and tool nodes. Define a provider interface, initially implemented for Anthropic and subsequently extended to Groq and local Ollama. Keep the baseline dependency-free. Require a final result through a dedicated submission tool and validate it against the records fetched by the current run.

Keep model and evidence budgets separate. Disable hidden API retries. Persist visible messages, model events, token usage, tool errors, and stop reasons. A failed run is an execution failure, not an abstention. Do not infer cost from missing usage or guessed pricing.

Provide one explicitly scripted graph demonstration for development without credentials. Reject scripted providers in the quality comparison runner.

## Consequences

The orchestration and boundaries can be exercised without paid model calls. The local Qwen run now provides an inspected development result; hosted adapters have mock-transport coverage only. Model quality is measured on the current development suite and is not established for production or unseen incidents.

The current cause vocabulary is intentionally small. Semantic support of citations is not checked by matching IDs; separate graders and human review remain necessary. This agent reads evidence and proposes next steps; it has no remediation capability.
