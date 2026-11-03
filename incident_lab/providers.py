"""Provider boundary: real API execution and a clearly labeled protocol demo."""

import os
from dataclasses import dataclass
from typing import Protocol


class ProviderError(RuntimeError):
    """A safe-to-display provider failure, without credentials or raw bodies."""


@dataclass(frozen=True)
class ModelReply:
    content: list[dict]
    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0
    usage_complete: bool = True


class ModelProvider(Protocol):
    name: str
    model: str
    live: bool

    def complete(self, *, system: str, messages: list[dict], tools: list[dict]) -> ModelReply: ...


class AnthropicProvider:
    name = "anthropic"
    live = True

    def __init__(self, model: str | None = None, max_output_tokens: int = 1024):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ProviderError("Set ANTHROPIC_API_KEY locally before using the live provider.")
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "")
        if not self.model.strip():
            raise ProviderError("Choose an available model with --model or ANTHROPIC_MODEL.")
        if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 4096:
            raise ValueError("max_output_tokens must be between 1 and 4096")
        self.max_output_tokens = max_output_tokens
        try:
            import anthropic
        except ImportError as error:
            raise ProviderError("Install agent dependencies with: uv sync --extra agent") from error
        self._sdk = anthropic
        # No hidden SDK retries: each model call budget unit is one attempt.
        self._client = anthropic.Anthropic(timeout=30.0, max_retries=0)

    def complete(self, *, system: str, messages: list[dict], tools: list[dict]) -> ModelReply:
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_output_tokens,
                system=system,
                messages=messages,
                tools=tools,
            )
        except self._sdk.APIError as error:
            raise ProviderError(
                f"Anthropic request failed ({type(error).__name__}); check local API configuration and access."
            ) from None
        usage = response.usage
        return ModelReply(
            content=[
                block.model_dump(mode="json", exclude_none=True) for block in response.content
            ],
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_tokens=(getattr(usage, "cache_read_input_tokens", 0) or 0)
            + (getattr(usage, "cache_creation_input_tokens", 0) or 0),
        )


class ScriptedDemoProvider:
    """Fixed messages for INC-007 only. No inference, API, or quality benchmark."""

    name = "scripted-demo"
    model = "hand-authored-protocol-example"
    live = False

    def __init__(self):
        self.turn = 0

    def complete(self, *, system: str, messages: list[dict], tools: list[dict]) -> ModelReply:
        self.turn += 1
        if self.turn == 1:
            return ModelReply(
                content=[
                    {
                        "type": "tool_use",
                        "id": "demo-logs",
                        "name": "get_logs",
                        "input": {"service": "orders-api"},
                    },
                    {
                        "type": "tool_use",
                        "id": "demo-metrics",
                        "name": "get_metrics",
                        "input": {"service": "orders-api"},
                    },
                    {
                        "type": "tool_use",
                        "id": "demo-deployments",
                        "name": "get_deployments",
                        "input": {"service": "orders-api"},
                    },
                    {
                        "type": "tool_use",
                        "id": "demo-docs",
                        "name": "search_runbooks",
                        "input": {
                            "service": "orders-api",
                            "query": "incident investigation missing evidence",
                            "limit": 2,
                        },
                    },
                ]
            )
        return ModelReply(
            content=[
                {
                    "type": "tool_use",
                    "id": "demo-submit",
                    "name": "submit_investigation",
                    "input": {
                        "status": "hypothesis",
                        "suspected_cause": "resource_exhaustion",
                        "explanation": "The replay log reports an exhausted connection pool; metrics show all 20 connections busy and a growing queue.",
                        "next_step": "Inspect connection lifetime and database capacity before proposing a change.",
                        "evidence_ids": ["log-pool", "metric-pool"],
                        "runbook_ids": ["investigation@1"],
                    },
                }
            ]
        )
