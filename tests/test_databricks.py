import json
from types import SimpleNamespace

import pytest
from mcp.types import CallToolResult, TextContent, Tool

from enterprise_agent import databricks as db

HOST = "https://example.cloud.databricks.com"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.cloud.databricks.com/api/2.0/mcp/sql",
        "https://attacker.example/api/2.0/mcp/sql",
        "https://example.cloud.databricks.com.evil.example/api/2.0/mcp/sql",
        "https://example.cloud.databricks.com/api/2.0/mcp/sql?token=secret",
        "https://user:password@example.cloud.databricks.com/api/2.0/mcp/sql",
        "https://example.cloud.databricks.com/api/2.0/secrets/list",
        "https://example.cloud.databricks.com/api/2.0/mcp/../secrets",
        "https://example.cloud.databricks.com/api/2.0/mcp/%2e%2e/secrets",
    ],
)
def test_remote_url_validation(url):
    with pytest.raises(ValueError):
        db.validate_server_url(url, HOST)


def config_file(tmp_path, allowed):
    path = tmp_path / "remote.json"
    path.write_text(
        json.dumps(
            {
                "servers": [
                    {
                        "name": "sales",
                        "url": HOST + "/api/2.0/mcp/genie/id",
                        "allowed_tools": allowed,
                    }
                ]
            }
        )
    )
    return path


async def test_remote_discovery_and_exact_allowlist(tmp_path, monkeypatch):
    calls = []

    class Client:
        async def alist_tools(self):
            return [
                Tool(
                    name="workspace_specific_search",
                    description="Search",
                    inputSchema={
                        "type": "object",
                        "required": ["query"],
                        "properties": {"query": {"type": "string"}},
                    },
                ),
                Tool(name="unapproved_write", inputSchema={"type": "object"}),
            ]

        async def acall_tool(self, name, arguments):
            calls.append((name, arguments))
            return CallToolResult(content=[TextContent(type="text", text='{"value":7}')])

    monkeypatch.setattr(db, "_client", lambda server, workspace: Client())
    workspace = SimpleNamespace(config=SimpleNamespace(host=HOST))
    path = config_file(tmp_path, ["workspace_specific_search"])
    discovery = await db.discover(path, workspace)
    assert discovery[0]["tools"][0]["allowed"]
    assert not discovery[0]["tools"][1]["allowed"]
    gateway = await db.managed_gateway(path, workspace, tmp_path / "audit.jsonl", "remote-test")
    assert len(gateway.specs) == 1
    alias = next(iter(gateway.specs))
    assert (await gateway.call(alias, {"query": "example"}))["data"]["value"] == 7
    assert calls == [("workspace_specific_search", {"query": "example"})]
    assert not (await gateway.call("unapproved_write", {}))["ok"]
    assert len(calls) == 1


async def test_empty_allowlist_denies_everything(tmp_path, monkeypatch):
    async def empty_tools():
        return []

    monkeypatch.setattr(
        db, "_client", lambda server, workspace: SimpleNamespace(alist_tools=empty_tools)
    )
    with pytest.raises(ValueError, match="No tools allowed"):
        await db.managed_gateway(
            config_file(tmp_path, []),
            SimpleNamespace(config=SimpleNamespace(host=HOST)),
            tmp_path / "audit.jsonl",
            "empty",
        )
