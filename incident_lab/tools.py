"""Allowlisted, read-only evidence tools with validated arguments and traces."""

from dataclasses import asdict
from time import perf_counter

from .models import Incident
from .replay import search_runbooks, visible_records


class ToolError(ValueError):
    pass


class ToolGateway:
    def __init__(self, incident: Incident, max_calls: int = 8):
        if type(max_calls) is not int or max_calls < 1:
            raise ValueError("max_calls must be a positive integer")
        self.incident = incident
        self.max_calls = max_calls
        self.trace: list[dict] = []

    def call(self, name: str, /, **arguments) -> list[dict]:
        started = perf_counter()
        span = {
            "sequence": len(self.trace) + 1,
            "tool": name,
            "arguments": arguments,
            "status": "ok",
            "evidence_ids": [],
        }
        try:
            if len(self.trace) >= self.max_calls:
                raise ToolError("Tool call budget exhausted")
            if name not in {"get_logs", "get_metrics", "get_deployments", "search_runbooks"}:
                raise ToolError(f"Tool is not allowed: {name}")
            allowed = {"service", "query", "limit"} if name == "search_runbooks" else {"service"}
            if set(arguments) - allowed:
                raise ToolError("Unexpected tool arguments")
            if arguments.get("service") != self.incident.service:
                raise ToolError("Tool access is restricted to the incident service")
            if name == "search_runbooks":
                query, limit = arguments.get("query"), arguments.get("limit", 3)
                if not isinstance(query, str) or not query.strip() or len(query) > 500:
                    raise ToolError("query must contain 1–500 characters")
                if type(limit) is not int or not 1 <= limit <= 10:
                    raise ToolError("limit must be an integer between 1 and 10")
            if name in self.incident.unavailable_tools:
                raise ToolError(f"Replay fault: {name} is unavailable")
            if name == "search_runbooks":
                result = [
                    {**asdict(item["record"]), "retrieval_score": item["score"]}
                    for item in search_runbooks(self.incident, query, limit)
                ]
            else:
                kind = {
                    "get_logs": "log",
                    "get_metrics": "metric",
                    "get_deployments": "deployment",
                }[name]
                result = [asdict(record) for record in visible_records(self.incident, kind)]
            span["evidence_ids"] = [item["id"] for item in result]
            return result
        except ToolError as error:
            span.update(status="error", error=str(error))
            raise
        finally:
            span["duration_ms"] = round((perf_counter() - started) * 1000, 3)
            self.trace.append(span)
