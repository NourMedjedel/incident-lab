"""Explicit operator commands; model tools have no write credentials."""

import json
from pathlib import Path

from .baseline import investigate
from .live import HTTPToolGateway, SandboxHTTPServer, request_json, running_sandbox
from .sandbox import SandboxError, SandboxStore


def add_commands(commands):
    live = commands.add_parser(
        "investigate-live", help="Investigate a running local sandbox using read-only HTTP tools"
    )
    live.add_argument("--url", default="http://127.0.0.1:8765")
    live.add_argument(
        "--provider", choices=["rules", "ollama", "groq", "anthropic"], default="rules"
    )
    live.add_argument("--model")
    live.add_argument("--output", default="artifacts/live-investigation.json")
    sandbox = commands.add_parser("sandbox", help="Run and operate the isolated local HTTP service")
    actions = sandbox.add_subparsers(dest="sandbox_command", required=True)
    serve = actions.add_parser("serve", help="Serve a local orders API and control API")
    serve.add_argument("--port", type=int, default=8765)
    demo = actions.add_parser("demo", help="Run a complete isolated fault/recovery demonstration")
    demo.add_argument(
        "--approve",
        action="store_true",
        help="Explicitly approve restoring the demo's known-good configuration",
    )
    demo.add_argument(
        "--provider", choices=["rules", "ollama", "groq", "anthropic"], default="rules"
    )
    demo.add_argument("--model")
    demo.add_argument("--output", default="artifacts/sandbox-demo.json")
    for name in ("probe", "inject", "propose", "approve", "execute", "audit"):
        command = actions.add_parser(name)
        command.add_argument("--url", default="http://127.0.0.1:8765")
        if name != "probe" and name != "audit":
            command.add_argument("--state-dir", default="artifacts/sandbox")
        if name == "inject":
            command.add_argument(
                "--fault",
                choices=["invalid_configuration", "telemetry_outage", "slow_telemetry"],
                required=True,
            )
        if name == "propose":
            command.add_argument("--investigation", required=True)
        if name in {"approve", "execute"}:
            command.add_argument("--proposal", required=True)
        if name == "approve":
            command.add_argument("--ttl", type=int, default=60)
        if name == "execute":
            command.add_argument("--idempotency-key")
    serve.add_argument("--state-dir", default="artifacts/sandbox")
    demo.add_argument("--state-dir", default="artifacts/sandbox-demo")


def control(url, path, body, token):
    status, result = request_json(url, path, method="POST", body=body, token=token)
    if status != 200:
        raise SandboxError(result.get("error", f"HTTP {status}"), status)
    return result


def investigate_live(url: str, provider_name: str, model: str | None) -> dict:
    gateway = HTTPToolGateway(url)
    if provider_name == "rules":
        return investigate(gateway.incident, gateway=gateway)
    from .agent import investigate_agent
    from .chat_providers import GroqProvider, OllamaProvider
    from .providers import AnthropicProvider

    provider = {"ollama": OllamaProvider, "groq": GroqProvider, "anthropic": AnthropicProvider}[
        provider_name
    ](model)
    return investigate_agent(gateway.incident, provider, gateway=gateway)


def propose_from_investigation(url, investigation, token):
    source = investigation.get("evidence_source", {})
    if (
        investigation.get("status") != "hypothesis"
        or investigation.get("suspected_cause") != "invalid_configuration"
        or source.get("kind") != "http-snapshot"
        or source.get("url") != url.rstrip("/")
    ):
        raise SandboxError("A local configuration hypothesis from this sandbox is required")
    return control(url, "/control/proposals", {"snapshot_id": source["snapshot_id"]}, token)


def execute_proposal(url, proposal, token, key=None):
    status, value = request_json(url, f"/control/proposals/{proposal}", token=token)
    if status != 200:
        raise SandboxError(value.get("error", "Could not load proposal"), status)
    return control(
        url,
        "/control/execute",
        {
            "proposal_id": proposal,
            "parameters": value["parameters"],
            "idempotency_key": key or proposal,
        },
        token,
    )


def write_output(path, value):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def run(args) -> int:
    if args.command == "investigate-live":
        result = investigate_live(args.url, args.provider, args.model)
        write_output(args.output, result)
        print(f"{result['status']}: {result['suspected_cause']} · {result['mode']}")
        print(f"Investigation: {args.output}")
        return 1 if result["status"] == "failed" else 0
    command = args.sandbox_command
    if command == "serve":
        if not 0 <= args.port <= 65535:
            raise SandboxError("Invalid server port", 400)
        store = SandboxStore(args.state_dir)
        server = SandboxHTTPServer(store, args.port)
        print(f"Local sandbox: {server.url}", flush=True)
        print(
            f"Private operator/executor tokens are stored in {args.state_dir}; do not share or commit them.",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    if command == "demo":
        # Each invocation gets fresh durable state. Prior demonstrations remain
        # available for inspection instead of being reset or overwritten.
        from uuid import uuid4

        store = SandboxStore(Path(args.state_dir) / uuid4().hex)
        with running_sandbox(store) as server:
            healthy = [request_json(server.url, "/orders")[0] for _ in range(3)]
            control(
                server.url,
                "/control/inject",
                {"fault": "invalid_configuration"},
                store.tokens["operator"],
            )
            broken = [request_json(server.url, "/orders")[0] for _ in range(3)]
            print(f"Actual HTTP /orders statuses: healthy={healthy}, fault={broken}", flush=True)
            investigation = investigate_live(server.url, args.provider, args.model)
            result = {
                "mode": "local-http-sandbox",
                "before_fault": healthy,
                "during_fault": broken,
                "investigation": investigation,
                "state_directory": str(store.directory),
            }
            if (
                investigation["status"] != "hypothesis"
                or investigation["suspected_cause"] != "invalid_configuration"
            ):
                write_output(args.output, result)
                print(f"Recovery not proposed; inspect {args.output}")
                return 1
            proposal = propose_from_investigation(
                server.url, investigation, store.tokens["executor"]
            )
            result["proposal"] = proposal
            print(
                "Exact proposed action: " + json.dumps(proposal["parameters"], sort_keys=True),
                flush=True,
            )
            if args.approve:
                result["approval"] = control(
                    server.url,
                    "/control/approve",
                    {"proposal_id": proposal["id"], "ttl_seconds": 60},
                    store.tokens["operator"],
                )
                result["execution"] = execute_proposal(
                    server.url, proposal["id"], store.tokens["executor"]
                )
                result["after_recovery"] = [
                    request_json(server.url, "/orders")[0] for _ in range(3)
                ]
                print(
                    f"Approved recovery verified with actual HTTP: {result['after_recovery']}",
                    flush=True,
                )
            else:
                print(
                    "No approval supplied: proposal remains pending and no recovery is executed.",
                    flush=True,
                )
            result["audit"] = store.audit_events()
            write_output(args.output, result)
            print(f"Demo evidence and audit: {args.output}", flush=True)
            return 1 if args.approve and not result["execution"]["verification"]["recovered"] else 0
    if command == "probe":
        statuses = [request_json(args.url, "/orders")[0] for _ in range(3)]
        print(
            json.dumps({"statuses": statuses, "healthy": all(status == 200 for status in statuses)})
        )
        return 0 if all(status == 200 for status in statuses) else 1
    if command == "audit":
        status, result = request_json(args.url, "/v1/audit")
        print(json.dumps(result, indent=2))
        return 0 if status == 200 else 1
    role = "operator" if command in {"inject", "approve"} else "executor"
    token = (Path(args.state_dir) / f"{role}.token").read_text(encoding="utf-8").strip()
    if command == "inject":
        result = control(args.url, "/control/inject", {"fault": args.fault}, token)
    elif command == "propose":
        result = propose_from_investigation(
            args.url, json.loads(Path(args.investigation).read_text(encoding="utf-8")), token
        )
    elif command == "approve":
        result = control(
            args.url,
            "/control/approve",
            {"proposal_id": args.proposal, "ttl_seconds": args.ttl},
            token,
        )
    else:
        result = execute_proposal(args.url, args.proposal, token, args.idempotency_key)
    print(json.dumps(result, indent=2))
    return 1 if command == "execute" and not result["verification"]["recovered"] else 0
