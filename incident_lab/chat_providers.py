"""Groq and local Ollama adapters; no fallback to another endpoint or provider."""

import json
import os
from uuid import uuid4

from .providers import ModelReply, ProviderError


def chat_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
        for tool in tools
    ]


def chat_messages(system: str, messages: list[dict], *, ollama: bool = False) -> list[dict]:
    """Translate the graph's tool protocol without losing call/result pairing."""
    translated = [{"role": "system", "content": system}]
    names = {}
    for message in messages:
        if isinstance(message["content"], str):
            translated.append({"role": message["role"], "content": message["content"]})
            continue
        text = []
        calls = []
        results = []
        for block in message["content"]:
            if block["type"] == "text":
                text.append(block["text"])
            elif block["type"] == "tool_use":
                names[block["id"]] = block["name"]
                function = {
                    "name": block["name"],
                    "arguments": block["input"] if ollama else json.dumps(block["input"]),
                }
                calls.append(
                    {
                        "type": "function",
                        "function": function,
                        **({} if ollama else {"id": block["id"]}),
                    }
                )
            elif block["type"] == "tool_result":
                content = block["content"]
                if block.get("is_error"):
                    content = json.dumps({"error": True, "message": content})
                result = {"role": "tool", "content": content}
                if ollama:
                    result["tool_name"] = names[block["tool_use_id"]]
                else:
                    result["tool_call_id"] = block["tool_use_id"]
                results.append(result)
        if calls or text:
            entry = {"role": message["role"], "content": "\n".join(text)}
            if calls:
                entry["tool_calls"] = calls
            translated.append(entry)
        translated.extend(results)
    return translated


def normalized_content(message: dict, *, ollama: bool = False) -> list[dict]:
    blocks = []
    if isinstance(message.get("content"), str) and message["content"]:
        blocks.append({"type": "text", "text": message["content"]})
    for call in message.get("tool_calls") or []:
        function = call["function"]
        arguments = function["arguments"]
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        blocks.append(
            {
                "type": "tool_use",
                "id": f"ollama-{uuid4().hex}" if ollama else call["id"],
                "name": function["name"],
                "input": arguments,
            }
        )
    return blocks


class ChatProvider:
    live = True  # Real inference, including local inference; not a scripted demo.

    def __init__(self, *, timeout: float):
        try:
            import httpx
        except ImportError as error:
            raise ProviderError("Install agent dependencies with: uv sync --extra agent") from error
        self._httpx = httpx
        self._client = httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False)

    def post(self, endpoint: str, payload: dict, headers: dict | None = None) -> dict:
        try:
            response = self._client.post(endpoint, json=payload, headers=headers)
        except self._httpx.HTTPError:
            raise ProviderError(
                f"{self.name} connection failed; check the configured service. No fallback was attempted."
            ) from None
        if response.status_code == 429:
            raise ProviderError(
                f"{self.name} rate limit reached (HTTP 429). Wait before retrying; no fallback was attempted."
            )
        if response.status_code != 200:
            raise ProviderError(
                f"{self.name} request failed (HTTP {response.status_code}); check model availability and configuration."
            )
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Expected an object")
            return data
        except ValueError:
            raise ProviderError(f"{self.name} returned an invalid JSON response.") from None


class GroqProvider(ChatProvider):
    name = "groq"

    def __init__(self, model: str | None = None):
        self._key = os.environ.get("GROQ_API_KEY", "")
        if not self._key:
            raise ProviderError(
                "Set GROQ_API_KEY locally. Use a Groq Free plan account for a no-cost prototype."
            )
        self.model = model or os.environ.get("GROQ_MODEL", "")
        if not self.model.strip():
            raise ProviderError(
                "Choose an available tool-calling model with --model or GROQ_MODEL."
            )
        super().__init__(timeout=30.0)

    def complete(self, *, system: str, messages: list[dict], tools: list[dict]) -> ModelReply:
        data = self.post(
            "https://api.groq.com/openai/v1/chat/completions",
            {
                "model": self.model,
                "messages": chat_messages(system, messages),
                "tools": chat_tools(tools),
                "tool_choice": "required",
                "max_completion_tokens": 1024,
                "stream": False,
            },
            headers={"Authorization": f"Bearer {self._key}"},
        )
        try:
            content = normalized_content(data["choices"][0]["message"])
            usage = data.get("usage") or {}
            cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
            return ModelReply(
                content=content,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                cache_tokens=cached,
                usage_complete="prompt_tokens" in usage and "completion_tokens" in usage,
            )
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise ProviderError("Groq returned an invalid tool-calling response.") from None


class OllamaProvider(ChatProvider):
    name = "ollama"

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("OLLAMA_MODEL", "")
        if not self.model.strip():
            raise ProviderError(
                "Choose an installed tool-calling model with --model or OLLAMA_MODEL."
            )
        if "cloud" in self.model.lower():
            raise ProviderError(
                "This adapter is local-only; choose a downloaded model without a cloud tag."
            )
        super().__init__(timeout=120.0)

    def complete(self, *, system: str, messages: list[dict], tools: list[dict]) -> ModelReply:
        # Fixed loopback endpoint, no proxy environment, credentials, or cloud fallback.
        data = self.post(
            "http://127.0.0.1:11434/api/chat",
            {
                "model": self.model,
                "messages": chat_messages(system, messages, ollama=True),
                "tools": chat_tools(tools),
                "stream": False,
                "think": False,
                "options": {"num_predict": 1024, "num_ctx": 8192, "temperature": 0},
            },
        )
        try:
            return ModelReply(
                content=normalized_content(data["message"], ollama=True),
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
                usage_complete="prompt_eval_count" in data and "eval_count" in data,
            )
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise ProviderError("Ollama returned an invalid tool-calling response.") from None
