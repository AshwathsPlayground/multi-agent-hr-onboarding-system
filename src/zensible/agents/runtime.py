"""Shared runtime helper for observable specialist model calls."""

import json
from collections.abc import Mapping

from zensible.domain.contracts import AgentName, ModelAssessment
from zensible.modeling import StructuredAgentModel
from zensible.observability import EventSink


async def model_assessment(
    model: StructuredAgentModel | None,
    *,
    agent: AgentName,
    context: Mapping[str, object],
) -> ModelAssessment | None:
    """Ask the injected provider for a validated advisory assessment."""

    if model is None:
        return None
    return await model.ainvoke(
        agent_name=agent.value,
        system_prompt=(
            "Assess the onboarding context for your specialist domain. Return a "
            "concise structured assessment. Do not invent facts or perform side effects."
        ),
        user_input=json.dumps(context, default=str, sort_keys=True),
        response_model=ModelAssessment,
    )


def record_result(events: EventSink | None, result: object) -> object:
    """Publish a specialist result without making it part of business state."""

    if events is not None:
        events.emit(
            "agent.result",
            result.agent.value,
            {"result": result.model_dump(mode="json")},
        )
    return result
