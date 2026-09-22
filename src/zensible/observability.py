"""Small, consistent tracing seam for graph nodes and agent methods.

Tracing is opt-in through LangSmith's native ``LANGCHAIN_TRACING_V2`` setting
and a configured ``LANGCHAIN_API_KEY``.  Keeping the gate here means offline
tests and local development do not create network work or require credentials.
"""

from __future__ import annotations

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
