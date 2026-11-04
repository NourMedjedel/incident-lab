"""Fixture access and keyword retrieval with an incident-time boundary."""

import hashlib
import json
import math
import re
from collections import Counter
from importlib.resources import files

from .models import Incident, Record, instant


def read_resource(name: str) -> dict:
    return json.loads(files("incident_lab").joinpath("data", name).read_text(encoding="utf-8"))


SUITES = {
    "development": ("incidents.json", "ground_truth.json"),
    "challenge": ("challenge_incidents.json", "challenge_labels.json"),
}


def suite_resources(suite: str) -> tuple[str, str]:
    if suite not in SUITES:
        raise ValueError(f"Unknown evaluation suite: {suite}")
    return SUITES[suite]


def fixture_manifest(suite: str = "development") -> dict[str, str]:
    """Identify the exact observations and labels used to score a run."""
    return {
        name: hashlib.sha256(files("incident_lab").joinpath("data", name).read_bytes()).hexdigest()
        for name in suite_resources(suite)
    }


def load_incidents(suite: str = "development") -> dict[str, Incident]:
    raw = read_resource(suite_resources(suite)[0])
    result = {}
    for case in raw["incidents"]:
        incident = Incident(
            id=case["id"],
            service=case["service"],
            title=case["title"],
            cutoff=case["cutoff"],
            records=tuple(Record(**record) for record in case["records"]),
            unavailable_tools=tuple(case.get("unavailable_tools", [])),
        )
        if incident.id in result:
            raise ValueError(f"Duplicate incident ID: {incident.id}")
        result[incident.id] = incident
    return result


def visible_records(incident: Incident, kind: str) -> list[Record]:
    return sorted(
        (
            r
            for r in incident.records
            if r.kind == kind
            and r.service == incident.service
            and instant(r.timestamp) <= instant(incident.cutoff)
        ),
        key=lambda r: (instant(r.timestamp), r.id),
    )


def tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", value.lower())


def search_runbooks(incident: Incident, query: str, limit: int) -> list[dict]:
    """BM25 over the latest visible version of each runbook ID.

    Runbook versions use ``document-name@version`` IDs. Filtering versions
    before scoring prevents future runbooks and duplicate versions leaking in.
    """
    latest = {}
    for record in visible_records(incident, "runbook"):
        latest[record.id.split("@")[0]] = record
    documents = list(latest.values())
    if not documents:
        return []
    terms = [Counter(tokens(doc.text)) for doc in documents]
    lengths = [sum(counts.values()) for counts in terms]
    average = sum(lengths) / len(documents)
    scored = []
    for document, counts, length in zip(documents, terms, lengths):
        score = 0.0
        for term in set(tokens(query)):
            frequency = counts[term]
            if not frequency:
                continue
            document_frequency = sum(term in item for item in terms)
            idf = math.log(
                1 + (len(documents) - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            score += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * length / average))
        if score:
            scored.append({"record": document, "score": round(score, 6)})
    return sorted(scored, key=lambda item: (-item["score"], item["record"].id))[:limit]
