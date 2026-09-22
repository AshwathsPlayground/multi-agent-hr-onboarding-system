"""Small, consistent tracing seam for graph nodes and agent methods.

Tracing is opt-in through LangSmith's native ``LANGCHAIN_TRACING_V2`` setting
and a configured ``LANGCHAIN_API_KEY``.  Keeping the gate here means offline
tests and local development do not create network work or require credentials.
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ParamSpec, Protocol, TypeVar, overload

from langsmith import traceable
from pydantic import JsonValue

P = ParamSpec("P")
R = TypeVar("R")

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    """Small, serializable event used by demos and test transcripts."""

    kind: str
    name: str
    payload: dict[str, JsonValue] = field(default_factory=dict)


class EventSink(Protocol):
    def emit(
        self,
        kind: str,
        name: str,
        payload: Mapping[str, JsonValue] | None = None,
    ) -> None: ...


class RecordingEventSink:
    """Collect observable model, tool, and graph events in execution order."""

    def __init__(self) -> None:
        self.events: list[ExecutionEvent] = []

    def emit(
        self,
        kind: str,
        name: str,
        payload: Mapping[str, JsonValue] | None = None,
    ) -> None:
        self.events.append(
            ExecutionEvent(kind=kind, name=name, payload=dict(payload or {}))
        )


class NullEventSink:
    """No-op event sink for callers that do not need a transcript."""

    def emit(
        self,
        kind: str,
        name: str,
        payload: Mapping[str, JsonValue] | None = None,
    ) -> None:
        del kind, name, payload


def format_event(event: ExecutionEvent) -> str:
    """Render one execution event as a compact reviewer-facing transcript line."""

    formatter = _EVENT_FORMATTERS.get(event.kind, _format_unknown)
    return formatter(event)


def render_events(events: Sequence[ExecutionEvent]) -> str:
    """Render a complete event sequence without exposing raw context blobs."""

    return "\n".join(format_event(event) for event in events)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mappings(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [_mapping(item) for item in value]


def _join_values(values: object) -> str:
    return (
        "; ".join(str(value) for value in values)
        if isinstance(values, Sequence)
        else str(values)
    )


def _compact_mapping(payload: Mapping[str, object]) -> str:
    return ", ".join(f"{key}={value}" for key, value in payload.items())


def _summarize_model_input(value: object) -> str:
    if not isinstance(value, str):
        return str(value)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value
    if not isinstance(parsed, Mapping):
        return str(parsed)

    fields = _request_fields(parsed) + _context_fields(parsed)
    return ", ".join(fields) or "structured context"


def _request_fields(parsed: Mapping[str, object]) -> list[str]:
    return _fields_for_keys(
        parsed,
        (
            "employee_reference",
            "requested_role",
            "requested_location",
            "requested_joining_date",
        ),
    )


def _fields_for_keys(parsed: Mapping[str, object], keys: Sequence[str]) -> list[str]:
    return [f"{key}={parsed[key]}" for key in keys if key in parsed]


def _context_fields(parsed: Mapping[str, object]) -> list[str]:
    return (
        _fields_for_keys(
            parsed,
            ("onboarding_id", "state_revision", "facts_version", "policy_version"),
        )
        + _optional_context_field(parsed, "validated_hr_facts", "employee_id")
        + _optional_context_field(parsed, "resume_event", "kind")
        + _collection_counts(parsed)
    )


def _optional_context_field(
    parsed: Mapping[str, object], key: str, nested_key: str
) -> list[str]:
    value = _mapping(parsed.get(key))
    return [f"{nested_key}={value.get(nested_key, 'n/a')}"] if value else []


def _collection_counts(parsed: Mapping[str, object]) -> list[str]:
    return [
        f"{key}={len(parsed[key])}"
        for key in ("existing_tasks", "existing_operations")
        if isinstance(parsed.get(key), Sequence)
        and not isinstance(parsed.get(key), str)
    ]


def _result_lines(result: Mapping[str, object]) -> list[str]:
    return (
        _finding_lines(result)
        + _missing_input_lines(result)
        + _conflict_lines(result)
        + _error_lines(result)
        + _payload_lines(_mapping(result.get("payload")))
        + _task_lines(result)
    )


def _finding_lines(result: Mapping[str, object]) -> list[str]:
    return [
        f"  Finding: {finding.get('code', 'n/a')} — {finding.get('message', 'n/a')}"
        for finding in _mappings(result.get("findings"))
    ]


def _missing_input_lines(result: Mapping[str, object]) -> list[str]:
    return [
        f"  Missing input: {missing.get('field', 'n/a')} — {missing.get('reason', 'n/a')}"
        for missing in _mappings(result.get("missing_inputs"))
    ]


def _conflict_lines(result: Mapping[str, object]) -> list[str]:
    return [
        f"  Conflict: {conflict.get('field', 'n/a')} "
        f"(resolution required={conflict.get('resolution_required', 'n/a')})"
        for conflict in _mappings(result.get("conflicts"))
    ]


def _error_lines(result: Mapping[str, object]) -> list[str]:
    return [
        f"  Error: {error.get('code', 'n/a')} — {error.get('message', 'n/a')}"
        for error in _mappings(result.get("errors"))
    ]


def _task_lines(result: Mapping[str, object]) -> list[str]:
    tasks = _mappings(result.get("proposed_tasks"))
    if not tasks:
        return []
    return [
        "  Proposed tasks: "
        + "; ".join(
            f"{task.get('intent', 'n/a')} ({task.get('task_id', 'n/a')})"
            for task in tasks
        )
    ]


def _payload_lines(payload: Mapping[str, object]) -> list[str]:
    formatters = (
        ("employee_id", _facts_payload),
        ("items", _provisioning_payload),
        ("requirements", _requirements_payload),
        ("eligible", _payroll_payload),
        ("status", _delivery_payload),
    )
    for key, formatter in formatters:
        if key in payload:
            return formatter(payload)
    return [f"  Payload: {_compact_mapping(payload)}"]


def _facts_payload(payload: Mapping[str, object]) -> list[str]:
    return [
        "  Facts: "
        + _pairs(payload, ("employee_id", "name", "role", "location", "joining_date"))
    ]


def _provisioning_payload(payload: Mapping[str, object]) -> list[str]:
    items = _mappings(payload.get("items"))
    return [
        "  Provisioning: "
        + "; ".join(
            f"{item.get('resource', 'n/a')}={item.get('status', 'n/a')}"
            for item in items
        )
    ]


def _requirements_payload(payload: Mapping[str, object]) -> list[str]:
    requirements = _mappings(payload.get("requirements"))
    return [
        "  Requirements: "
        + "; ".join(
            f"{requirement.get('code', 'n/a')}={requirement.get('status', 'n/a')}"
            for requirement in requirements
        )
    ]


def _payroll_payload(payload: Mapping[str, object]) -> list[str]:
    return [
        "  Payroll: "
        + _pairs(
            payload, ("eligible", "compensation_reference", "bank_details_reference")
        )
    ]


def _delivery_payload(payload: Mapping[str, object]) -> list[str]:
    return [f"  Delivery: status={payload.get('status')}"]


def _pairs(payload: Mapping[str, object], keys: Sequence[str]) -> str:
    return "; ".join(
        f"{key}={payload.get(key)}" for key in keys if payload.get(key) is not None
    )


def _format_model_request(event: ExecutionEvent) -> str:
    return "\n".join(
        (
            f"[MODEL REQUEST] {event.name} provider={event.payload.get('provider', 'unknown')}",
            f"  Input: {_summarize_model_input(event.payload.get('input'))}",
        )
    )


def _format_model_response(event: ExecutionEvent) -> str:
    output = _mapping(event.payload.get("output"))
    evidence = output.get("evidence", [])
    lines = [
        f"[MODEL RESPONSE] {event.name} provider={event.payload.get('provider', 'unknown')}",
        f"  Summary: {output.get('summary', 'n/a')}",
        f"  Recommendation: {output.get('recommendation', 'n/a')}",
        f"  Confidence: {output.get('confidence', 'n/a')}",
    ]
    return "\n".join(
        lines + [f"  Evidence: {_join_values(evidence)}"] if evidence else lines
    )


def _format_agent_result(event: ExecutionEvent) -> str:
    result = _mapping(event.payload.get("result"))
    model_output = _mapping(result.get("model_output"))
    model_lines = (
        [
            (
                f"  Model: {model_output.get('summary', 'n/a')} "
                f"(confidence={model_output.get('confidence', 'n/a')})"
            )
        ]
        if model_output
        else []
    )
    header = (
        f"[AGENT RESULT] {event.name} outcome={result.get('outcome', 'n/a')} "
        f"phase={result.get('phase', 'n/a')} revision={result.get('state_revision', 'n/a')}"
    )
    return "\n".join([header] + model_lines + _result_lines(result))


def _format_tool_request(event: ExecutionEvent) -> str:
    return (
        f"[TOOL REQUEST] {event.name} task={event.payload.get('task_id', 'n/a')} "
        f"operation={event.payload.get('operation_key', 'n/a')}"
    )


def _format_tool_response(event: ExecutionEvent) -> str:
    replayed = " replayed" if event.payload.get("replayed") else ""
    reference = event.payload.get("external_reference") or "none"
    return (
        f"[TOOL RESPONSE] {event.name} status={event.payload.get('status', 'n/a')} "
        f"reference={reference}{replayed}"
    )


def _format_unknown(event: ExecutionEvent) -> str:
    return f"[{event.kind.upper()}] {event.name} {_compact_mapping(event.payload)}"


_EVENT_FORMATTERS: dict[str, Callable[[ExecutionEvent], str]] = {
    "model.request": _format_model_request,
    "model.response": _format_model_response,
    "agent.result": _format_agent_result,
    "tool.request": _format_tool_request,
    "tool.response": _format_tool_response,
}


def tracing_enabled() -> bool:
    """Return whether this process has explicitly enabled LangSmith tracing.

    The API key check is intentional: it prevents an accidental network
    attempt when a developer enables tracing but has not configured credentials.
    """

    return os.getenv(
        "LANGCHAIN_TRACING_V2", ""
    ).strip().lower() in _TRUE_VALUES and bool(
        os.getenv("LANGCHAIN_API_KEY", "").strip()
    )


@overload
def trace_operation(
    operation_name: str,
    *,
    metadata: Mapping[str, Any] | None = None,
    tags: Sequence[str] | None = None,
    run_type: str = "chain",
    enabled: bool | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


@overload
def trace_operation(
    operation_name: str,
    *,
    metadata: Mapping[str, Any] | None = None,
    tags: Sequence[str] | None = None,
    run_type: str = "chain",
    enabled: bool | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]: ...


def trace_operation(
    operation_name: str,
    *,
    metadata: Mapping[str, Any] | None = None,
    tags: Sequence[str] | None = None,
    run_type: str = "chain",
    enabled: bool | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorate a callable with one stable LangSmith operation name.

    Both synchronous and asynchronous callables are supported because the
    native LangSmith decorator handles either shape.  ``enabled`` is useful for
    tests and controlled deployments; when omitted, the environment gate from
    :func:`tracing_enabled` is used.  Metadata and tags are attached to every
    invocation of the decorated operation.
    """

    if not operation_name.strip():
        raise ValueError("operation_name must not be empty")

    should_trace = tracing_enabled() if enabled is None else enabled

    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        if not should_trace:
            return function

        traced = traceable(
            name=operation_name,
            run_type=run_type,
            metadata=dict(metadata) if metadata else None,
            tags=list(tags) if tags else None,
        )(function)
        return traced

    return decorate
