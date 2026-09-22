"""Small seam for swapping deterministic and live structured model adapters."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from zensible.config import Settings
from zensible.llm import build_chat_model
from zensible.observability import EventSink, NullEventSink

ResponseT = TypeVar("ResponseT", bound=BaseModel)
ScriptedResponse = BaseModel | Mapping[str, Any]


class StructuredAgentModel(Protocol):
    """Interface shared by fake and live structured agent-model adapters."""

    async def ainvoke(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        user_input: str,
        response_model: type[ResponseT],
    ) -> ResponseT: ...


@dataclass(frozen=True, slots=True)
class StructuredAgentCall:
    """Observable request details retained by the scripted adapter."""

    agent_name: str
    system_prompt: str
    user_input: str


class ScriptedStructuredAgentModel:
    """Deterministic provider that returns scripted, validated responses."""

    def __init__(
        self,
        responses: Mapping[str, ScriptedResponse | Sequence[ScriptedResponse]],
        *,
        events: EventSink | None = None,
    ) -> None:
        self._responses = {
            agent_name: self._as_queue(response)
            for agent_name, response in responses.items()
        }
        self.calls: list[StructuredAgentCall] = []
        self._events = events or NullEventSink()

    @staticmethod
    def _as_queue(
        response: ScriptedResponse | Sequence[ScriptedResponse],
    ) -> deque[ScriptedResponse]:
        if isinstance(response, (BaseModel, Mapping)):
            return deque([response])
        return deque(response)

    async def ainvoke(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        user_input: str,
        response_model: type[ResponseT],
    ) -> ResponseT:
        try:
            responses = self._responses[agent_name]
        except KeyError as error:
            raise KeyError(
                f"No scripted response configured for '{agent_name}'"
            ) from error

        if not responses:
            raise RuntimeError(
                f"Scripted response sequence is empty for '{agent_name}'"
            )

        response = responses[0] if len(responses) == 1 else responses.popleft()
        self.calls.append(
            StructuredAgentCall(
                agent_name=agent_name,
                system_prompt=system_prompt,
                user_input=user_input,
            )
        )
        self._events.emit(
            "model.request",
            agent_name,
            {"provider": "fake", "input": user_input},
        )
        result = _validate_response(response_model, response)
        self._events.emit(
            "model.response",
            agent_name,
            {"provider": "fake", "output": result.model_dump(mode="json")},
        )
        return result


class LangChainStructuredAgentModel:
    """Live adapter backed by the configured OpenAI-compatible ChatOpenAI model."""

    def __init__(self, settings: Settings, *, events: EventSink | None = None) -> None:
        self._chat_model = build_chat_model(settings)
        self._events = events or NullEventSink()

    async def ainvoke(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        user_input: str,
        response_model: type[ResponseT],
    ) -> ResponseT:
        self._events.emit(
            "model.request",
            agent_name,
            {"provider": "live", "input": user_input},
        )
        structured_model = self._chat_model.with_structured_output(response_model)
        response = await structured_model.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_input),
            ]
        )
        result = _validate_response(response_model, response)
        self._events.emit(
            "model.response",
            agent_name,
            {"provider": "live", "output": result.model_dump(mode="json")},
        )
        return result


def _validate_response[T: BaseModel](response_model: type[T], response: Any) -> T:
    if isinstance(response, response_model):
        return response
    return response_model.model_validate(response)


__all__ = [
    "LangChainStructuredAgentModel",
    "ScriptedStructuredAgentModel",
    "StructuredAgentCall",
    "StructuredAgentModel",
]
