"""Optional MLflow ResponsesAgent entrypoint; requires the Databricks extra.

Single-turn, read-only adapter. The deployment's configured Databricks identity
is used; custom_inputs never select a role, host, tool allowlist, or credentials.
"""

import asyncio
import os
import uuid

import mlflow
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import ResponsesAgentRequest, ResponsesAgentResponse

from enterprise_agent.agent import ask
from enterprise_agent.databricks import chat_model, managed_gateway, workspace_client


class EnterpriseResponsesAgent(ResponsesAgent):
    async def _answer(self, question: str):
        workspace = workspace_client(os.getenv("DATABRICKS_CONFIG_PROFILE"))
        model = chat_model(workspace, os.environ["DATABRICKS_MODEL_ENDPOINT"])
        gateway = await managed_gateway(
            os.environ["MCP_SERVER_CONFIG"],
            workspace,
            os.getenv("MCP_AUDIT_PATH", "logs/audit.jsonl"),
            uuid.uuid4().hex,
        )
        return await ask(model, gateway, question)

    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        # Explicitly single-turn; reject other roles rather than trust injected system text.
        if len(request.input) != 1 or request.input[0].role != "user":
            raise ValueError("Send exactly one user message; this adapter is single-turn")
        content = request.input[0].content
        if isinstance(content, str):
            question = content
        else:
            texts = []
            for block in content:
                item = block if isinstance(block, dict) else block.model_dump()
                if item.get("type") != "input_text":
                    raise ValueError("Only text input is supported")
                texts.append(item["text"])
            question = "\n".join(texts)
        result = asyncio.run(self._answer(question))
        return ResponsesAgentResponse(
            output=[self.create_text_output_item(text=str(result["answer"]), id=uuid.uuid4().hex)],
            custom_outputs={"run_id": result["run_id"], "tool_calls": result["tool_calls"]},
        )


mlflow.models.set_model(EnterpriseResponsesAgent())
