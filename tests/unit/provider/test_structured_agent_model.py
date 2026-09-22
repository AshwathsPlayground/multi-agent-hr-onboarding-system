from collections.abc import Mapping

import pytest
from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from zensible.config import Settings
from zensible.modeling.provider import (
    LangChainStructuredAgentModel,
    ScriptedStructuredAgentModel,
)


class Greeting(BaseModel):
    message: str
    confidence: float


@pytest.mark.asyncio
async def test_scripted_model_validates_response_and_records_call() -> None:
    model = ScriptedStructuredAgentModel(
        {"hr": {"message": "employee validated", "confidence": 0.99}}
    )

    result = await model.ainvoke(
        agent_name="hr",
        system_prompt="Return HR facts.",
        user_input="Validate employee 42.",
        response_model=Greeting,
    )

    assert result == Greeting(message="employee validated", confidence=0.99)
    assert model.calls[0].agent_name == "hr"
    assert model.calls[0].user_input == "Validate employee 42."


@pytest.mark.asyncio
async def test_scripted_model_supports_ordered_responses() -> None:
    model = ScriptedStructuredAgentModel(
        {
            "hr": [
                {"message": "first", "confidence": 0.7},
                {"message": "second", "confidence": 0.8},
            ]
        }
    )

    first = await model.ainvoke(
        agent_name="hr",
        system_prompt="system",
        user_input="first input",
        response_model=Greeting,
    )
    second = await model.ainvoke(
        agent_name="hr",
        system_prompt="system",
        user_input="second input",
        response_model=Greeting,
    )

    assert first.message == "first"
    assert second.message == "second"


@pytest.mark.asyncio
async def test_scripted_model_rejects_unknown_agent() -> None:
    model = ScriptedStructuredAgentModel({})

    with pytest.raises(KeyError, match="No scripted response configured for 'hr'"):
        await model.ainvoke(
            agent_name="hr",
            system_prompt="system",
            user_input="input",
            response_model=Greeting,
        )


@pytest.mark.asyncio
async def test_scripted_model_reuses_last_response_after_sequence() -> None:
    model = ScriptedStructuredAgentModel(
        {
            "hr": [
                {"message": "first response", "confidence": 0.7},
                {"message": "second response", "confidence": 0.8},
            ]
        }
    )
    await model.ainvoke(
        agent_name="hr",
        system_prompt="system",
        user_input="first input",
        response_model=Greeting,
    )
    await model.ainvoke(
        agent_name="hr",
        system_prompt="system",
        user_input="second input",
        response_model=Greeting,
    )

    third = await model.ainvoke(
        agent_name="hr",
        system_prompt="system",
        user_input="third input",
        response_model=Greeting,
    )

    assert third.message == "second response"


@pytest.mark.asyncio
async def test_scripted_model_rejects_invalid_structured_response() -> None:
    model = ScriptedStructuredAgentModel({"hr": {"message": "missing confidence"}})

    with pytest.raises(ValueError):
        await model.ainvoke(
            agent_name="hr",
            system_prompt="system",
            user_input="input",
            response_model=Greeting,
        )


class _FakeStructuredRunnable:
    def __init__(self, response: Mapping[str, object]) -> None:
        self.response = response
        self.messages: list[BaseMessage] | None = None

    async def ainvoke(self, messages: list[BaseMessage]) -> Mapping[str, object]:
        self.messages = messages
        return self.response


class _FakeChatModel:
    def __init__(self, runnable: _FakeStructuredRunnable) -> None:
        self.runnable = runnable
        self.response_model: type[BaseModel] | None = None

    def with_structured_output(
        self, response_model: type[BaseModel]
    ) -> _FakeStructuredRunnable:
        self.response_model = response_model
        return self.runnable


@pytest.mark.asyncio
async def test_live_adapter_uses_existing_chat_model_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runnable = _FakeStructuredRunnable(
        {"message": "employee validated", "confidence": 0.95}
    )
    chat_model = _FakeChatModel(runnable)
    monkeypatch.setattr(
        "zensible.modeling.provider.build_chat_model",
        lambda settings: chat_model,
    )

    model = LangChainStructuredAgentModel(Settings(_env_file=None))
    result = await model.ainvoke(
        agent_name="hr",
        system_prompt="Return HR facts.",
        user_input="Validate employee 42.",
        response_model=Greeting,
    )

    assert result == Greeting(message="employee validated", confidence=0.95)
    assert chat_model.response_model is Greeting
    assert runnable.messages is not None
    assert [message.content for message in runnable.messages] == [
        "Return HR facts.",
        "Validate employee 42.",
    ]
