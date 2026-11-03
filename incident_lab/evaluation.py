"""Ground truth is used only after an investigation returns its prediction."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from platform import python_version

from .baseline import investigate
from .replay import fixture_manifest, load_incidents, read_resource


def evaluate(investigator=None, *, engine: str = "rules-v1") -> dict:
    runner = investigator or investigate
    incidents = load_incidents()
    labels = read_resource("ground_truth.json")["labels"]
    if set(labels) != set(incidents):
        raise ValueError("Every incident must have exactly one evaluation label")
    cases = []
    for incident_id, incident in incidents.items():
        prediction = runner(incident)
        label = labels[incident_id]
        answered = prediction["suspected_cause"] is not None
        completed = prediction["status"] in {"hypothesis", "abstained"}
        correct = completed and prediction["suspected_cause"] == label["cause"]
        cited = set(prediction["evidence_ids"])
        required = set(label["required_evidence"])
        # An empty reference set does not establish support for an invented
        # diagnosis on an expected-abstention case.
        supported = bool(cited) and required <= cited if answered and required else None
        retrieved = {record["id"] for record in prediction["runbooks"][:2]}
        relevant = set(label["relevant_runbooks"])
        cases.append(
            {
                "incident_id": incident_id,
                "slice": label["slice"],
                "expected_cause": label["cause"],
                "predicted_cause": prediction["suspected_cause"],
                "status": prediction["status"],
                "correct": correct,
                "stop_reason": prediction.get("stop_reason"),
                "required_evidence_cited": supported,
                "runbook_recall_at_2": len(retrieved & relevant) / len(relevant)
                if relevant
                else None,
                "llm_calls": prediction["measurement"]["llm_calls"],
                "input_tokens": prediction["measurement"].get("input_tokens", 0),
                "output_tokens": prediction["measurement"].get("output_tokens", 0),
                "usage_complete": prediction["measurement"].get("usage_complete", True),
                "estimated_llm_cost_usd": prediction["measurement"].get(
                    "estimated_llm_cost_usd", prediction["measurement"].get("llm_cost_usd")
                ),
                "duration_ms": prediction["measurement"]["duration_ms"],
                "tool_errors": prediction["tool_errors"],
            }
        )

    answers = [case for case in cases if case["predicted_cause"] is not None]
    evidence_evaluated = [case for case in answers if case["required_evidence_cited"] is not None]
    diagnoses = [case for case in cases if case["expected_cause"] is not None]
    abstentions = [case for case in cases if case["expected_cause"] is None]
    recall_values = [
        case["runbook_recall_at_2"] for case in cases if case["runbook_recall_at_2"] is not None
    ]
    return {
        "engine": engine,
        "fixture_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python_version": python_version(),
        "scope": "Small synthetic development suite; not a held-out or production benchmark.",
        "summary": {
            "case_count": len(cases),
            "behavior_correct_count": sum(case["correct"] for case in cases),
            "answered_count": len(answers),
            "answer_coverage": len(answers) / len(cases),
            "diagnostic_recall": sum(case["correct"] for case in diagnoses) / len(diagnoses)
            if diagnoses
            else None,
            "accuracy_when_answered": sum(case["correct"] for case in answers) / len(answers)
            if answers
            else None,
            "appropriate_abstention_rate": sum(case["correct"] for case in abstentions)
            / len(abstentions)
            if abstentions
            else None,
            "required_evidence_evaluated_count": len(evidence_evaluated),
            "required_evidence_coverage_when_answered": sum(
                case["required_evidence_cited"] for case in evidence_evaluated
            )
            / len(evidence_evaluated)
            if evidence_evaluated
            else None,
            "mean_runbook_recall_at_2": sum(recall_values) / len(recall_values)
            if recall_values
            else None,
            "llm_calls": sum(case["llm_calls"] for case in cases),
            "failed_count": sum(case["status"] == "failed" for case in cases),
            "input_tokens": sum(case["input_tokens"] for case in cases),
            "output_tokens": sum(case["output_tokens"] for case in cases),
            "usage_complete": all(case["usage_complete"] for case in cases),
            "estimated_llm_cost_usd": sum(case["estimated_llm_cost_usd"] for case in cases)
            if all(case["estimated_llm_cost_usd"] is not None for case in cases)
            else None,
        },
        "cases": cases,
    }


def render_report(result: dict) -> str:
    summary = result["summary"]
    rows = [
        "# Incident Lab: baseline evaluation",
        "",
        result["scope"],
        "",
        f"Engine: `{result['engine']}` · Fixtures: `{result['fixture_version']}` · Python: `{result['python_version']}`",
        "",
        f"Behavior matches: **{summary['behavior_correct_count']}/{summary['case_count']}**. "
        f"Answered: **{summary['answered_count']}/{summary['case_count']}**. "
        f"LLM calls: **{summary['llm_calls']}**.",
        "",
        "A correct abstention counts as a behavior match. Coverage and diagnostic recall "
        "must be considered alongside accuracy on answered cases.",
        "",
        "| Case | Expected | Predicted | Match |",
        "| --- | --- | --- | --- |",
    ]
    for case in result["cases"]:
        rows.append(
            f"| {case['incident_id']} | {case['expected_cause'] or 'abstain'} | "
            f"{case['predicted_cause'] or 'abstain'} | {'yes' if case['correct'] else 'no'} |"
        )
    rows += [
        "",
        "The fixtures were written with the baseline and are development examples, "
        "not independent evidence of generalization. Pool exhaustion is a deliberately "
        "unsupported case: it should expose the baseline's limited coverage.",
        "",
    ]
    return "\n".join(rows)


def compare(provider, *, progress=None, **agent_options) -> dict:
    from .agent import investigate_agent

    if not provider.live:
        raise ValueError("Scripted demonstrations cannot be used as model-quality benchmarks")
    traces = {}

    def runner(incident):
        if progress:
            progress(f"Investigating {incident.id}: {incident.title}")
        result = investigate_agent(incident, provider, **agent_options)
        traces[incident.id] = result
        if progress:
            progress(f"  {result['status']} · {result['measurement']['model_turns']} model turns")
        return result

    return {
        "scope": "Synthetic development cases; results do not establish production effectiveness.",
        "provider": provider.name,
        "model": provider.model,
        "provenance": {"fixture_sha256": fixture_manifest(), "source": "new-inference"},
        "baseline": evaluate(),
        "agent": evaluate(runner, engine="langgraph-agent-v1"),
        "agent_traces": traces,
    }


def replay_comparison(path: str | Path) -> dict:
    """Regrade recorded predictions offline; never instantiate a model provider."""
    source = Path(path)
    try:
        raw_bytes = source.read_bytes()
        saved = json.loads(raw_bytes)
        if not isinstance(saved, dict):
            raise ValueError("The artifact must be a JSON object")
        if saved.get("provenance", {}).get("fixture_sha256") != fixture_manifest():
            raise ValueError(
                "Fixture hashes do not match this checkout; use the source version matching the artifact"
            )
        if saved.get("provider") not in {"ollama", "groq", "anthropic"}:
            raise ValueError(
                "Replay requires a recorded real-model comparison, not scripted messages"
            )
        incidents = load_incidents()
        traces = saved["agent_traces"]
        if not isinstance(traces, dict) or set(traces) != set(incidents):
            raise ValueError("The artifact must contain exactly one trace for every fixture")
        for id, incident in incidents.items():
            trace = traces[id]
            if (
                trace["incident_id"] != id
                or trace["service"] != incident.service
                or trace["as_of"] != incident.cutoff
                or trace["provider"] != saved["provider"]
                or trace["model"] != saved["model"]
                or trace["engine"] != "langgraph-agent-v1"
                or trace["mode"] != "synthetic-fixture-replay"
                or trace["status"] not in {"hypothesis", "abstained", "failed"}
            ):
                raise ValueError(
                    "Recorded trace metadata is inconsistent with the artifact or fixtures"
                )
        result = {
            **saved,
            "scope": "Offline replay of saved predictions; no new inference. Recorded timings and token usage are historical.",
            "baseline": evaluate(),
            "agent": evaluate(lambda incident: traces[incident.id], engine="langgraph-agent-v1"),
            "replay": {
                "source_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "new_model_requests": 0,
            },
        }
        return result
    except OSError as error:
        raise ValueError(f"Cannot read comparison artifact: {source}") from error
    except (KeyError, TypeError, AttributeError, UnicodeDecodeError) as error:
        raise ValueError(
            "Invalid saved comparison structure; use a complete comparison JSON artifact"
        ) from error


def render_comparison(result: dict) -> str:
    rows = [
        "# Incident Lab: baseline vs agent",
        "",
        result["scope"],
        "",
        f"Provider: `{result['provider']}` · Model: `{result['model']}`",
        "",
        "| Measure | Rules | Agent |",
        "| --- | --- | --- |",
    ]
    for key in (
        "behavior_correct_count",
        "answered_count",
        "diagnostic_recall",
        "failed_count",
        "llm_calls",
        "input_tokens",
        "output_tokens",
        "estimated_llm_cost_usd",
    ):
        values = [result[engine]["summary"][key] for engine in ("baseline", "agent")]
        rows.append(
            f"| {key} | {values[0] if values[0] is not None else 'unknown'} | "
            f"{values[1] if values[1] is not None else 'unknown'} |"
        )
    rows += [
        "",
        "Execution failures count as incorrect, including on expected-abstention cases. "
        "Unknown cost is not zero. Any provided rates yield an estimate, not an invoice. "
        "Full JSON includes per-case outcomes and agent traces.",
        "",
    ]
    if "replay" in result:
        rows += [
            "This report regrades recorded predictions. Model-request counts, timings, and "
            "token usage describe the original run; replay made zero model requests.",
            "",
        ]
    return "\n".join(rows)
