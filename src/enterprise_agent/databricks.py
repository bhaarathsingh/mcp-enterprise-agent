"""Opt-in managed MCP adapter. Tool names and schemas come from the workspace."""

import asyncio
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from enterprise_agent.audit import AuditLog
from enterprise_agent.clients import ToolGateway, ToolSpec


def validate_server_url(url: str, host: str) -> None:
    target, workspace = urlsplit(url), urlsplit(host)
    if (
        target.scheme != "https"
        or target.hostname != workspace.hostname
        or target.port != workspace.port
        or target.username
        or target.password
        or target.query
        or target.fragment
        or not target.path.startswith(("/api/2.0/mcp/", "/ai-gateway/mcp-services/"))
        or "/../" in target.path
        or "%" in target.path
    ):
        raise ValueError("MCP URL must be a managed endpoint on the authenticated workspace host")


def load_config(path: str | Path, host: str) -> list[dict]:
    config = json.loads(Path(path).read_text())
    servers = config.get("servers")
    if not isinstance(servers, list) or not 1 <= len(servers) <= 8:
        raise ValueError("Configure 1 to 8 MCP servers")
    names = set()
    for server in servers:
        name = server.get("name", "")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,19}", name) or name in names:
            raise ValueError("Server names must be unique short lowercase identifiers")
        names.add(name)
        validate_server_url(server["url"], host)
        allowed = server.get("allowed_tools")
        if not isinstance(allowed, list) or any(not isinstance(t, str) for t in allowed):
            raise ValueError("Each server needs an explicit allowed_tools list; [] denies all")
    return servers


def workspace_client(profile: str | None = None):
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient(profile=profile) if profile else WorkspaceClient()


def chat_model(workspace, endpoint: str):
    if not endpoint:
        raise ValueError("Set DATABRICKS_MODEL_ENDPOINT to a tool-calling serving endpoint")
    from databricks_langchain import ChatDatabricks

    return ChatDatabricks(
        endpoint=endpoint,
        workspace_client=workspace,
        temperature=0,
        max_tokens=1200,
        timeout=40,
        max_retries=0,
    )


def _client(server: dict, workspace):
    from databricks_mcp import DatabricksMCPClient

    return DatabricksMCPClient(server_url=server["url"], workspace_client=workspace)


async def discover(config: str | Path, workspace) -> list[dict]:
    rows = []
    for server in load_config(config, workspace.config.host):
        client = _client(server, workspace)
        async with asyncio.timeout(30):
            tools = await client.alist_tools()
        rows.append(
            {
                "server": server["name"],
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "schema": t.inputSchema,
                        "allowed": t.name in server["allowed_tools"],
                    }
                    for t in tools
                ],
            }
        )
    return rows


async def managed_gateway(
    config: str | Path, workspace, audit_path: str | Path, run_id: str
) -> ToolGateway:
    specs, routes = [], {}
    for server in load_config(config, workspace.config.host):
        client = _client(server, workspace)
        async with asyncio.timeout(30):
            tools = await client.alist_tools()
        found = {tool.name for tool in tools}
        if set(server["allowed_tools"]) - found:
            raise ValueError(
                f"Allowlisted tool missing from server {server['name']}; rediscover tools"
            )
        for tool in tools:
            if tool.name not in server["allowed_tools"]:
                continue
            # Fixed-length namespace avoids collisions and provider name limits.
            digest = hashlib.sha256(tool.name.encode()).hexdigest()[:16]
            alias = f"{server['name']}__{digest}"
            if alias in routes:
                raise ValueError("Tool alias collision")
            routes[alias] = (client, tool.name)
            specs.append(
                ToolSpec(
                    alias,
                    f"{server['name']}: {tool.name}. " + (tool.description or ""),
                    tool.inputSchema,
                )
            )
    if not specs:
        raise ValueError("No tools allowed. Run discover, then approve exact read-only tool names")

    async def call(name, arguments):
        client, original = routes[name]
        return await client.acall_tool(original, arguments)

    return ToolGateway(
        specs,
        call,
        audit=AuditLog(audit_path),
        principal="databricks-configured-identity",
        run_id=run_id,
        timeout=30,
    )
