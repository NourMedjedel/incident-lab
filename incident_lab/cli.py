import argparse
import json
import sys
from pathlib import Path

from .baseline import investigate
from .evaluation import compare, evaluate, render_comparison, render_report, replay_comparison
from .providers import ProviderError
from .replay import load_incidents


def write_json(path: str, value: dict) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Incident Lab: read-only investigation baseline and bounded agent"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List synthetic incident fixtures")
    demo = commands.add_parser("demo", help="Replay one incident with the rules baseline")
    demo.add_argument("--scenario", default="INC-001")
    demo.add_argument("--output", help="Write the full JSON evidence trace")
    benchmark = commands.add_parser("evaluate", help="Evaluate all synthetic development fixtures")
    benchmark.add_argument("--output", default="artifacts/evaluation.json")
    benchmark.add_argument("--report", default="artifacts/evaluation.md")
    replay = commands.add_parser(
        "replay", help="Regrade a saved comparison offline; no model or API key"
    )
    replay.add_argument("artifact", help="Path to a saved comparison JSON file")
    replay.add_argument("--output", default="artifacts/replayed-comparison.json")
    replay.add_argument("--report", default="artifacts/replayed-comparison.md")
    offline = commands.add_parser(
        "agent-demo", help="Run hand-authored messages through the agent graph; no inference or API"
    )
    offline.add_argument("--output", default="artifacts/scripted-agent-demo.json")
    agent = commands.add_parser(
        "agent", help="Run an investigator with Groq, local Ollama, or Anthropic"
    )
    agent.add_argument("--scenario", default="INC-001")
    agent.add_argument("--output", default="artifacts/agent-trace.json")
    comparison = commands.add_parser(
        "compare", help="Compare a real model against the rules on eight cases"
    )
    comparison.add_argument("--output", default="artifacts/comparison.json")
    comparison.add_argument("--report", default="artifacts/comparison.md")
    for command in (agent, comparison):
        command.add_argument(
            "--provider",
            choices=["groq", "ollama", "anthropic"],
            default="groq",
            help="Model backend (default: groq; account must be on Free plan for no-cost use)",
        )
        command.add_argument(
            "--model",
            help="Model ID; defaults to the selected provider's MODEL environment variable",
        )
        command.add_argument(
            "--max-model-calls", type=int, default=6, help="Per-incident API attempt limit (1–20)"
        )
        command.add_argument(
            "--max-tool-calls", type=int, default=8, help="Per-incident evidence tool budget (1–32)"
        )
        command.add_argument(
            "--input-rate",
            type=float,
            help="Optional input USD per million tokens; supply with --output-rate",
        )
        command.add_argument(
            "--output-rate", type=float, help="Optional output USD per million tokens"
        )
    args = parser.parse_args(argv)

    if args.command == "list":
        for incident in load_incidents().values():
            print(f"{incident.id}: {incident.title}")
        return 0

    if args.command == "evaluate":
        result = evaluate()
        write_json(args.output, result)
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(render_report(result), encoding="utf-8")
        print(render_report(result))
        print(f"Full results: {args.output}")
        print(f"Report: {args.report}")
        # Unsupported diagnostic cases are reported, not silently excluded.
        # Expected development-suite misses are not a CI pass/fail threshold.
        return 0

    if args.command == "replay":
        try:
            result = replay_comparison(args.artifact)
            write_json(args.output, result)
            report = Path(args.report)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(render_comparison(result), encoding="utf-8")
        except (ValueError, OSError) as error:
            print(f"Replay error: {error}", file=sys.stderr)
            return 2
        print(render_comparison(result))
        print(f"Regraded results: {args.output}")
        print(f"Report: {args.report}")
        # A preserved model failure is an evaluation observation, not a replay failure.
        return 0

    if args.command in {"agent", "compare", "agent-demo"}:
        from .agent import investigate_agent
        from .chat_providers import GroqProvider, OllamaProvider
        from .providers import AnthropicProvider, ScriptedDemoProvider

        try:
            options = {}
            if args.command == "agent-demo":
                print(
                    "SCRIPTED PROTOCOL DEMO: hand-authored responses, no inference, no API, no model benchmark."
                )
                provider = ScriptedDemoProvider()
                scenario = "INC-007"
            else:
                provider = {
                    "groq": GroqProvider,
                    "ollama": OllamaProvider,
                    "anthropic": AnthropicProvider,
                }[args.provider](model=args.model)
                scenario = getattr(args, "scenario", None)
                options = {
                    "max_model_calls": args.max_model_calls,
                    "max_tool_calls": args.max_tool_calls,
                    "input_rate": args.input_rate,
                    "output_rate": args.output_rate,
                }
            if args.command == "compare":
                result = compare(
                    provider, progress=lambda message: print(message, flush=True), **options
                )
                write_json(args.output, result)
                report = Path(args.report)
                report.parent.mkdir(parents=True, exist_ok=True)
                report.write_text(render_comparison(result), encoding="utf-8")
                print(render_comparison(result))
                print(f"Full results and traces: {args.output}")
                return 1 if result["agent"]["summary"]["failed_count"] else 0
            incidents = load_incidents()
            if scenario not in incidents:
                parser.error(
                    f"Unknown scenario {scenario!r}; use 'list' to see available incidents"
                )
            result = investigate_agent(incidents[scenario], provider, **options)
        except (ProviderError, ValueError) as error:
            print(f"Configuration error: {error}", file=sys.stderr)
            return 2
        write_json(args.output, result)
        print(
            f"Engine: {result['engine']} | Status: {result['status']} | Stop: {result['stop_reason']}"
        )
        print(f"Suspected cause: {result['suspected_cause'] or 'undetermined'}")
        print(result["explanation"])
        print(f"Evidence: {', '.join(result['evidence_ids']) or 'none'}")
        print(
            f"Model turns: {result['measurement']['model_turns']} | Model requests: {result['measurement']['llm_calls']}"
        )
        print(f"Full protocol and evidence trace: {args.output}")
        return 1 if result["status"] == "failed" else 0

    incidents = load_incidents()
    if args.scenario not in incidents:
        parser.error(f"Unknown scenario {args.scenario!r}; use 'list' to see available incidents")
    result = investigate(incidents[args.scenario])
    print(f"Incident Lab | {result['incident_id']} | {result['mode']}")
    print(f"Engine: {result['engine']} (no LLM calls)")
    print(f"Service: {result['service']} | Evidence cutoff: {result['as_of']}")
    print(f"Status: {result['status']}")
    print(f"Suspected cause: {result['suspected_cause'] or 'undetermined'}")
    print(result["explanation"])
    print(f"Next step: {result['next_step']}")
    print("\nCited evidence:")
    for record in result["evidence"]:
        print(f"  [{record['id']}] {record['timestamp']} {record['text']}")
    if not result["evidence"]:
        print("  No supported diagnostic evidence.")
    print("\nRetrieved runbooks:")
    for record in result["runbooks"]:
        print(f"  [{record['id']}] {record['text']}")
    print("\nTool trace:")
    for span in result["trace"]:
        print(
            f"  {span['sequence']}. {span['tool']}: {span['status']} "
            f"({len(span['evidence_ids'])} records, {span['duration_ms']} ms)"
        )
        if span.get("error"):
            print(f"     {span['error']}")
    print("\nFixture replay; hypotheses are not proven root causes. No action was executed.")
    if args.output:
        write_json(args.output, result)
        print(f"Full trace: {args.output}")
    return 0
