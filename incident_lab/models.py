"""Immutable replay inputs. Ground truth is intentionally a separate resource."""

from dataclasses import dataclass
from datetime import datetime


def instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Evidence timestamps must include a timezone")
    return parsed


@dataclass(frozen=True)
class Record:
    id: str
    kind: str
    service: str
    timestamp: str
    text: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.id, self.kind, self.service, self.timestamp, self.text)
        ):
            raise ValueError("Evidence fields must be nonempty strings")
        instant(self.timestamp)
        if self.kind not in {"log", "metric", "deployment", "runbook"}:
            raise ValueError(f"Unknown evidence kind: {self.kind}")
        if not all((self.id, self.service, self.text)):
            raise ValueError("Evidence id, service, and text must be nonempty")


@dataclass(frozen=True)
class Incident:
    id: str
    service: str
    title: str
    cutoff: str
    records: tuple[Record, ...]
    unavailable_tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.id, self.service, self.title, self.cutoff)
        ):
            raise ValueError("Incident metadata must contain nonempty strings")
        instant(self.cutoff)
        ids = [record.id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("Evidence IDs must be unique within an incident")
