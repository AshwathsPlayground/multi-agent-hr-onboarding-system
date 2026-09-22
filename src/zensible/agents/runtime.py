"""Shared runtime helper for observable specialist model calls."""

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from zensible.domain.contracts import (
    AgentDecision,
    AgentName,
    ErrorDetail,
    MissingInput,
    ModelAssessment,
    SpecialistOutcome,
    SpecialistResult,
)
from zensible.modeling import StructuredAgentModel
from zensible.observability import EventSink

_SENSITIVE_FIELD_MARKERS = (
    "bank_details",
    "account_number",
    "routing_number",
    "ssn",
    "tax_id",
    "secret",
    "token",
    "api_key",
)


def _redact_model_context(value: object, *, field_name: str | None = None) -> object:
    if field_name is not None and any(
        marker in field_name.lower() for marker in _SENSITIVE_FIELD_MARKERS
    ):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(key): _redact_model_context(item, field_name=str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_model_context(item) for item in value]
    return value


async def model_assessment(
    model: StructuredAgentModel | None,
    *,
    agent: AgentName,
    context: Mapping[str, object],
    candidate_task_ids: Sequence[str] = (),
) -> ModelAssessment | None:
    """Ask the injected provider for validated, bounded agent guidance."""

    if model is None:
        return None
    model_context = _redact_model_context(dict(context))
    if not isinstance(model_context, Mapping):
        raise TypeError("model context must be a mapping")
    if candidate_task_ids:
        model_context["candidate_task_ids"] = list(candidate_task_ids)
    try:
        return await model.ainvoke(
            agent_name=agent.value,
            system_prompt=(
                f"You are the {agent.value} onboarding specialist. Assess the supplied "
                "context and return structured guidance. Choose decision=proceed only "
                "when the current candidate work is safe, decision=request_input when "
                "authoritative information is missing, or decision=escalate when human "
                "review is required. If candidate_task_ids are supplied, approved_task_ids "
                "must contain only candidate IDs you recommend; use null when you do not "
                "need to choose tasks. A request_input decision may approve safe "
                "independent candidates while deferring work that needs the requested "
                "input. Treat deterministic_* fields in the context as "
                "authoritative domain validation; do not add requirements solely because "
                "a source field or candidate list is not included. Do not invent facts "
                "or perform side effects."
            ),
            user_input=json.dumps(model_context, default=str, sort_keys=True),
            response_model=ModelAssessment,
        )
    except Exception as error:  # noqa: BLE001 - provider boundary must be contained
        # A provider outage is a bounded review outcome, not permission to run
        # actions without model guidance or crash before checkpointing state.
        return ModelAssessment(
            summary=f"{agent.value} model assessment was unavailable",
            recommendation="Pause this specialist for human or provider recovery.",
            confidence=0.0,
            decision=AgentDecision.ESCALATE,
            escalation_reasons=[
                f"structured model provider failure: {type(error).__name__}"
            ],
        )


def apply_model_guidance(
    result: SpecialistResult[Any],
    *,
    model_output: ModelAssessment | None,
    candidate_task_ids: Sequence[str] = (),
) -> SpecialistResult[Any]:
    """Apply model guidance without allowing it to bypass deterministic policy."""

    if model_output is None:
        return result

    errors = list(result.errors)
    missing_inputs = list(result.missing_inputs)
    proposed_tasks = list(result.proposed_tasks)
    deferred_tasks = list(result.deferred_tasks)
    outcome = result.outcome

    def defer(tasks: Iterable[Any]) -> None:
        known_ids = {task.task_id for task in deferred_tasks}
        deferred_tasks.extend(task for task in tasks if task.task_id not in known_ids)

    if model_output.approved_task_ids is not None:
        candidate_tasks = list(proposed_tasks)
        approved = set(model_output.approved_task_ids)
        candidates = set(candidate_task_ids)
        unknown = approved - candidates
        if unknown:
            errors.append(
                ErrorDetail(
                    code="invalid_model_output",
                    message=(
                        f"{result.agent.value} model selected unknown task IDs: "
                        f"{sorted(unknown)}"
                    ),
                )
            )
            defer(candidate_tasks)
            proposed_tasks = []
            outcome = SpecialistOutcome.NEEDS_RESOLUTION
        else:
            defer(task for task in candidate_tasks if task.task_id not in approved)
            proposed_tasks = [
                task for task in candidate_tasks if task.task_id in approved
            ]

    if model_output.decision is AgentDecision.REQUEST_INPUT:
        had_domain_missing_inputs = bool(missing_inputs)
        requested_inputs = model_output.requested_inputs or [
            MissingInput(
                field=f"{result.agent.value}.model_review",
                reason=model_output.recommendation,
                requested_from=result.agent.value,
            )
        ]
        known_inputs = {(item.field, item.reason) for item in missing_inputs}
        missing_inputs.extend(
            item
            for item in requested_inputs
            if (item.field, item.reason) not in known_inputs
        )
        if model_output.approved_task_ids is None:
            defer(proposed_tasks)
            proposed_tasks = []
        if not had_domain_missing_inputs and outcome not in {
            SpecialistOutcome.NEEDS_RESOLUTION,
            SpecialistOutcome.FAILED,
        }:
            outcome = SpecialistOutcome.NEEDS_INPUT

    elif model_output.decision is AgentDecision.ESCALATE:
        reasons = model_output.escalation_reasons or [model_output.recommendation]
        errors.extend(
            ErrorDetail(code="model_escalation", message=reason) for reason in reasons
        )
        defer(proposed_tasks)
        proposed_tasks = []
        outcome = SpecialistOutcome.NEEDS_RESOLUTION

    return result.model_copy(
        update={
            "outcome": outcome,
            "errors": errors,
            "missing_inputs": missing_inputs,
            "proposed_tasks": proposed_tasks,
            "deferred_tasks": deferred_tasks,
            "model_output": model_output,
        }
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
