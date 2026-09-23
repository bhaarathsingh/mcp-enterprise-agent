import asyncio

from langchain_core.messages import AIMessage
from mcp.types import CallToolResult, TextContent

from enterprise_agent.agent import ask
from enterprise_agent.audit import AuditLog
from enterprise_agent.clients import ToolGateway, ToolSpec, unpack_result


class LoopModel:
    def bind_tools(self, schemas):
        return self

    async def ainvoke(self, messages):
        return AIMessage(
            content="",
            tool_calls=[
                {"id": str(len(messages)), "name": "example", "args": {}, "type": "tool_call"}
            ],
        )


def make_gateway(tmp_path, callback, timeout=1):
    return ToolGateway(
        [ToolSpec("example", "test", {"type": "object"})],
        callback,
        audit=AuditLog(tmp_path / "audit.jsonl"),
        principal="test",
        run_id="test",
        timeout=timeout,
    )


async def test_loop_stops_at_tool_budget(tmp_path):
    invoked = []

    async def call(name, args):
        invoked.append(name)
        return CallToolResult(content=[TextContent(type="text", text='{"value": 1}')])

    result = await ask(LoopModel(), make_gateway(tmp_path, call), "test", max_calls=2)
    assert len(invoked) == 2
    assert "limit" in result["answer"]


async def test_tool_timeout_is_sanitized_without_retry(tmp_path):
    invoked = []

    async def slow(name, args):
        invoked.append(name)
        await asyncio.sleep(1)

    result = await make_gateway(tmp_path, slow, timeout=0.01).call("example", {})
    assert not result["ok"]
    assert "timed out" in result["error"]
    assert len(invoked) == 1


async def test_backend_exception_is_not_disclosed(tmp_path):
    async def failing(name, args):
        raise RuntimeError("secret database password")

    result = await make_gateway(tmp_path, failing).call("example", {})
    assert "secret" not in str(result)
    assert not result["ok"]


def test_large_and_error_results_are_not_sent_to_model():
    too_large = CallToolResult(content=[TextContent(type="text", text="x" * 25000)])
    assert not unpack_result(too_large)["ok"]
    error = CallToolResult(isError=True, content=[TextContent(type="text", text="secret")])
    assert "secret" not in str(unpack_result(error))


async def test_model_timeout_does_not_dispatch_tools(tmp_path):
    class SlowModel(LoopModel):
        async def ainvoke(self, messages):
            await asyncio.sleep(1)

    async def must_not_call(name, args):
        raise AssertionError("Unexpected call")

    result = await ask(
        SlowModel(), make_gateway(tmp_path, must_not_call), "test", model_timeout=0.01
    )
    assert result["tool_calls"] == 0
    assert "timed out" in result["answer"]
