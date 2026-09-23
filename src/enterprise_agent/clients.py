"""MCP transport plus an explicit tool allowlist and schema gate."""

import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from enterprise_agent.audit import AuditLog
from enterprise_agent.policy import TOOL_ROLES, principal_named


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: dict

    def model_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema,
            },
        }


def unpack_result(result: Any) -> dict:
    if result.isError:
        # Tool errors are not fed back verbatim; they can contain backend details.
        return {"ok": False, "error": "Tool rejected the request or failed"}
    data = result.structuredContent
    if data is None:
        texts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
        if len(texts) == 1:
            try:
                data = json.loads(texts[0])
            except json.JSONDecodeError:
                data = {"text": texts[0]}
        else:
            data = {"text": "\n".join(texts)}
    if len(json.dumps(data).encode()) > 24_000:
        return {"ok": False, "error": "Result exceeds 24 KB; narrow the query"}
    return {"ok": True, "data": data}


class ToolGateway:
    def __init__(
        self,
        specs: list[ToolSpec],
        call,
        *,
        audit: AuditLog,
        principal: str,
        run_id: str,
        timeout: float = 15,
    ):
        self.specs = {s.name: s for s in specs}
        self._call = call
        self.audit = audit
        self.principal = principal
        self.run_id = run_id
        self.timeout = timeout

    async def call(self, name: str, arguments: dict) -> dict:
        status = "error"
        started = time.monotonic()
        # Log a fixed value for an unrecognized, model-supplied name.
        log_name = name if name in self.specs else "unlisted-tool"
        self.audit.record(
            principal=self.principal, tool=log_name, status="gateway_started", run_id=self.run_id
        )
        try:
            if name not in self.specs:
                status = "gateway_denied"
                return {"ok": False, "error": "Tool is not permitted in this session"}
            Draft202012Validator(self.specs[name].schema).validate(arguments)
            async with asyncio.timeout(self.timeout):
                response = await self._call(name, arguments)
            result = unpack_result(response)
            status = "gateway_success" if result["ok"] else "gateway_error"
            return result
        except ValidationError:
            status = "gateway_invalid"
            return {"ok": False, "error": "Arguments do not match the tool schema"}
        except TimeoutError:
            status = "gateway_timeout"
            return {"ok": False, "error": "Tool timed out; no automatic retry was attempted"}
        except Exception:
            status = "gateway_error"
            return {"ok": False, "error": "Tool unavailable; consult the operator"}
        finally:
            self.audit.record(
                principal=self.principal,
                tool=log_name,
                status=status,
                run_id=self.run_id,
                duration_ms=(time.monotonic() - started) * 1000,
            )


@asynccontextmanager
async def local_gateway(principal: str, audit_path: str | Path, run_id: str):
    identity = principal_named(principal)
    # The demo subprocess receives no cloud credentials from its parent.
    allowed_env = {
        k: v
        for k, v in os.environ.items()
        if k in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PYTHONPATH"}
    }
    allowed_env.update(
        {
            "MCP_DEMO_PRINCIPAL": principal,
            "MCP_AUDIT_PATH": str(Path(audit_path).resolve()),
            "MCP_RUN_ID": run_id,
            "PYTHONUNBUFFERED": "1",
        }
    )
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "enterprise_agent.server"], env=allowed_env
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(
            read, write, read_timeout_seconds=timedelta(seconds=20)
        ) as session:
            await session.initialize()
            specs = []
            cursor = None
            while True:
                page = await session.list_tools(cursor=cursor)
                for tool in page.tools:
                    if identity.role in TOOL_ROLES.get(tool.name, set()):
                        schema = {**tool.inputSchema, "additionalProperties": False}
                        specs.append(ToolSpec(tool.name, tool.description or "", schema))
                cursor = page.nextCursor
                if not cursor:
                    break
            yield ToolGateway(
                specs,
                session.call_tool,
                audit=AuditLog(audit_path),
                principal=principal,
                run_id=run_id,
            )
