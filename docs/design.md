# Design and operating limits

## Why this design

The boundary that matters is the tool server, not the wording of the system prompt.
The local server binds one principal at startup and checks policy again on every
business tool call. A direct MCP client cannot bypass the margin or region checks.
The client also removes unauthorized tools from the model's tool catalog and validates
arguments before dispatch.

The synthetic data is intentionally small: five documents, seven orders, and two
customer records. Exact integer cents avoid floating-point aggregation errors.
No SQL engine is needed for the local demo. Its analytics tools are structured
functions, not a simulation of Genie-generated SQL.

The retrieval index uses only documents visible to the current role. Filtering before
calculating TF-IDF means a confidential document cannot change another role's ranking
statistics. Search is lexical, so synonyms and paraphrases can fail to match. It is
not an embedding model. For larger collections, use a real managed Search index and
enforce appropriate data entitlements in Databricks.

## Run lifecycle

1. The CLI selects demo configuration or an authenticated Databricks profile.
2. The client discovers tools and their schemas.
3. The gateway exposes only the configured allowlist to the model.
4. LangGraph requests a model decision, validates calls, and invokes MCP tools.
5. Tool results return as evidence, and the model continues or answers.
6. A trace and request ID accompany the final answer.

The default budget is eight attempted tool dispatches and four model rounds.
Local calls time out after 15 seconds; remote calls after 30 seconds; model decisions
after 45 seconds. Results larger than 24 KB are rejected and the model is asked to
narrow the query. Errors are sanitized and are never automatically retried.

## Identity and authorization

The local identity selector is for demonstrating policies. It is not authentication
and is not exposed through an HTTP API. File owners can edit the source and data.

Databricks calls run as the configured SDK identity. Unity Catalog and the managed
MCP service enforce that identity's actual grants. Sharing one privileged service
principal across all users would share its privileges; this project does not implement
end-user OAuth delegation. A multi-user deployment needs verified identity propagation
or a deliberately restricted service identity and separately designed application policy.

The allowlist is explicit and starts empty. Only an operator edits it, not a model.
Review tool behavior before adding a remote name: an allowlist does not prove a remote
tool is read-only. Tool annotations are hints and are not a security boundary.
Remote server URLs are constrained to the authenticated workspace host and recognized
MCP paths. Custom external MCP servers are outside this MVP.

## Audit and failure behavior

JSONL records contain principal label, tool name, status, UTC timestamp, duration, and
run ID. They omit tool arguments, user questions, document bodies, and backend exception
messages. The model receives actual authorized results; auditing them is a separate
data-retention decision.

The gateway and local service record both started and terminal events. They propagate
audit write failures rather than silently returning data. Invalid MCP protocol requests
rejected before a handler are not covered by the service's business audit. Local files
are not immutable, centralized audit storage. Provision private directories and ship
records to an access-controlled sink before production use.

The adapter uses the Databricks SDK asynchronous MCP methods. A timeout cancels the
local await, but does not guarantee cancellation of work already accepted by the remote
server. The adapter has no retry loop and should only allow read-only tools.

## What the tests establish

- Exact local revenue and margin arithmetic.
- Region filtering and role denial at the server, including raw MCP calls.
- Document filtering before ranking and consistent inaccessible-customer responses.
- Masked customer contact data and metadata-only audit contents.
- Bounded tool loops, timeout behavior, sanitized errors, and schema enforcement.
- Actual stdio protocol initialization, tool discovery, and multi-tool agent runs.
- Databricks URL checks and routing with controlled SDK responses.

The injection test proves that a demo prompt cannot alter the configured principal.
It is not proof that a live language model resists all prompt injection. Prompt
instructions help the model interpret sources; deterministic tool policy contains
access even if the model makes a poor decision.

## Not claimed

No measured enterprise scale, uptime, business savings, live-user adoption, security
certification, Databricks resource provisioning, or production deployment. There is
no browser UI, distributed queue, durable conversation store, or write-tool approval flow.

Highest-value next step: run the adapter against a small Databricks workspace with
two differently privileged OAuth identities and record actual denied and allowed results.
