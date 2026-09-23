import argparse
import asyncio
import json
import os
import sys
import uuid

from enterprise_agent.agent import ask
from enterprise_agent.clients import local_gateway
from enterprise_agent.demo import DemoPlanner
from enterprise_agent.policy import PRINCIPALS


def parser():
    root = argparse.ArgumentParser(description="MCP Enterprise Agent — local lab and Databricks")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("demo", "ask", "tools", "discover"):
        command = commands.add_parser(name)
        command.add_argument("--principal", choices=PRINCIPALS, default="analyst-east")
        command.add_argument("--audit", default=os.getenv("MCP_AUDIT_PATH", "logs/audit.jsonl"))
        command.add_argument("--json", action="store_true", dest="as_json")
        if name in ("demo", "ask"):
            command.add_argument(
                "question", nargs="?", default="What is East revenue and the refund policy?"
            )
        if name in ("ask", "discover"):
            command.add_argument("--config", default="config/databricks.json")
            command.add_argument("--profile", default=os.getenv("DATABRICKS_CONFIG_PROFILE"))
        if name == "ask":
            command.add_argument("--tools", choices=["local", "databricks"], default="databricks")
            command.add_argument("--endpoint", default=os.getenv("DATABRICKS_MODEL_ENDPOINT", ""))
    return root


async def run(args):
    run_id = uuid.uuid4().hex
    if args.command in ("demo", "tools"):
        async with local_gateway(args.principal, args.audit, run_id) as gateway:
            if args.command == "tools":
                return {"principal": args.principal, "tools": list(gateway.specs)}
            return {
                "mode": "deterministic-demo",
                "principal": args.principal,
                **await ask(DemoPlanner(), gateway, args.question),
            }
    from enterprise_agent.databricks import chat_model, discover, managed_gateway, workspace_client

    workspace = workspace_client(args.profile)
    if args.command == "discover":
        return await discover(args.config, workspace)
    model = chat_model(workspace, args.endpoint)
    if args.tools == "local":
        async with local_gateway(args.principal, args.audit, run_id) as gateway:
            return {
                "mode": "databricks-model-local-tools",
                **await ask(model, gateway, args.question),
            }
    gateway = await managed_gateway(args.config, workspace, args.audit, run_id)
    return {"mode": "databricks", **await ask(model, gateway, args.question)}


def main():
    args = parser().parse_args()
    try:
        result = asyncio.run(run(args))
    except ImportError:
        print('Missing dependencies. Install: pip install -e ".[databricks]"', file=sys.stderr)
        raise SystemExit(2) from None
    except (ValueError, OSError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    except Exception:
        print(
            "Connection or configuration failed. Check your OAuth profile, endpoint, "
            "server config, and audit path.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    if args.as_json or not isinstance(result, dict) or "answer" not in result:
        print(json.dumps(result, indent=2))
    else:
        print(result["answer"])
        print(f"\nRun: {result['run_id']} | Tool calls: {result['tool_calls']}")
        for item in result["trace"]:
            print(f"  {'OK' if item['ok'] else 'BLOCKED/ERROR'}  {item['tool']}")


if __name__ == "__main__":
    main()
