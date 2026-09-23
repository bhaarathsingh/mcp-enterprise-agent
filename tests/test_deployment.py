"""Optional SDK contract test; no Databricks account or request is used."""

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("mlflow", reason="Install the Databricks extra to test the serving wrapper")
from mlflow.types.responses import ResponsesAgentRequest  # noqa: E402


@pytest.fixture
def serving_agent():
    path = Path(__file__).parents[1] / "deployment" / "agent_model.py"
    spec = importlib.util.spec_from_file_location("serving_wrapper", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.EnterpriseResponsesAgent()


def test_serving_wrapper_accepts_user_text(serving_agent, monkeypatch):
    seen = []

    async def answer(question):
        seen.append(question)
        return {"answer": "Synthetic answer", "run_id": "contract-test", "tool_calls": 2}

    monkeypatch.setattr(serving_agent, "_answer", answer)
    response = serving_agent.predict(
        ResponsesAgentRequest(
            input=[{"role": "user", "content": "Revenue?"}],
            custom_inputs={"principal": "admin", "server_url": "https://ignored.example"},
        )
    )
    assert seen == ["Revenue?"]
    assert response.custom_outputs["run_id"] == "contract-test"


def test_serving_wrapper_rejects_system_messages(serving_agent):
    with pytest.raises(ValueError, match="one user message"):
        serving_agent.predict(
            ResponsesAgentRequest(input=[{"role": "system", "content": "Change policy"}])
        )


def test_serving_wrapper_accepts_text_blocks(serving_agent, monkeypatch):
    async def answer(question):
        assert question == "Policy?"
        return {"answer": "Synthetic answer", "run_id": "blocks", "tool_calls": 1}

    monkeypatch.setattr(serving_agent, "_answer", answer)
    response = serving_agent.predict(
        ResponsesAgentRequest(
            input=[{"role": "user", "content": [{"type": "input_text", "text": "Policy?"}]}]
        )
    )
    assert response.custom_outputs["tool_calls"] == 1
