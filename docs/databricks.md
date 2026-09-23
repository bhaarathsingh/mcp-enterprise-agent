# Connect a Databricks workspace

The screenshot's stack requires actual Databricks resources. Local Python code cannot
provision or validate your workspace without its authentication and permissions.
This guide is an integration path, not a claim of deployment.

## Prerequisites

- An authenticated Databricks SDK/CLI profile.
- A model-serving endpoint that supports tool calling.
- A small document Search index with managed embeddings, a Genie space for analytics,
  and optionally a read-only Unity Catalog function.
- Appropriate grants for the identity used by the SDK.

Availability and billing depend on your workspace. Managed MCP features may be in preview.
Use the endpoint URLs shown in your workspace; Databricks documentation and product
names evolve. The supplied config uses the current managed AI Search endpoint family;
workspaces exposing the earlier Vector Search route can use the URL they provide.

## Local connection

```bash
python -m pip install -e ".[databricks]"
databricks auth login --host https://YOUR-WORKSPACE.cloud.databricks.com
export DATABRICKS_CONFIG_PROFILE=DEFAULT
export DATABRICKS_MODEL_ENDPOINT=YOUR_TOOL_CALLING_ENDPOINT
cp config/databricks.example.json config/databricks.json
```

The Databricks CLI is a separate prerequisite, not installed by this package.
Use OAuth through the CLI. Never put credentials into the repository or tool arguments.
The example environment file is documentation; the application does not load it automatically.

Edit `config/databricks.json` with workspace-provided URLs and remove server entries you
do not have. Discovery lists tools but does not call them:

```bash
enterprise-agent discover --config config/databricks.json
```

Review the actual tool descriptions and input schemas. Copy exact read-only names
into each server's `allowed_tools`. Empty lists deny everything. Names differ by
resource, so the project does not invent them. Then run:

```bash
enterprise-agent ask "Find the refund policy and summarize permitted revenue" \
  --config config/databricks.json --json
```

Tool aliases presented to the model include a server namespace and a stable hash.
The adapter retains the exact original name for execution and the live JSON schema
for validation. This prevents collisions across multiple servers.

## Verify governance before deployment

Create two test profiles with different grants. Run the same question using
`--profile RESTRICTED` and `--profile FINANCE`. Confirm that denied data does not
appear in the result, underlying service access is actually denied, and sources and
metrics are correct. Do not substitute the local `--principal` flag for Unity Catalog
permissions; it applies only to the local demo tools.

For Search, verify table/index entitlements and any necessary row or document filters.
Do not assume that granting access to an index automatically enforces the exact
document-level policy your application needs.

## Agent Framework entrypoint

`deployment/agent_model.py` wraps the graph in MLflow `ResponsesAgent` for integration
with Databricks agent tooling. It accepts exactly one user text message and deliberately
rejects user-supplied system messages. `custom_inputs` cannot change the identity or URLs.

Set these operator-controlled values in your serving environment:

| Variable | Purpose |
| --- | --- |
| `DATABRICKS_MODEL_ENDPOINT` | Tool-calling model endpoint |
| `MCP_SERVER_CONFIG` | Path to the reviewed MCP server configuration |
| `MCP_AUDIT_PATH` | Writable audit sink path for this MVP |
| `DATABRICKS_CONFIG_PROFILE` | Local development profile, when applicable |

Provision a deployment identity through Databricks authentication. Do not ship your local
OAuth cache. Package `src/enterprise_agent`, its data resources, reviewed config, and
the optional dependencies with the entrypoint. Follow Databricks' current agent packaging
and resource-authentication documentation to log and deploy it. This repository does
not auto-create paid serving endpoints or grant permissions.

A production deployment also needs a durable audit destination, per-user authorization
design, integration evaluation, tracing/retention policy, dependency review, and load tests.
The wrapper is single-turn and does not implement streaming or durable chat history.

## Official references

- [MCP clients and OAuth](https://docs.databricks.com/aws/en/agents/mcp-tools/use-mcp-in-agents)
- [Managed server URLs and scopes](https://docs.databricks.com/aws/en/agents/mcp-tools/managed-mcp)
- [Author and deploy agents](https://docs.databricks.com/aws/en/agents/custom-agents/author-agent)
- [MCP SDK API](https://api-docs.databricks.com/python/databricks-ai-bridge/latest/databricks_mcp.html)
- [ChatDatabricks API](https://api-docs.databricks.com/python/databricks-ai-bridge/latest/databricks_langchain.html)
