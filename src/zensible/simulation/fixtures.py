"""Deterministic in-memory enterprise services for offline execution."""

from dataclasses import dataclass
from enum import Enum

from pydantic import JsonValue


class FailureMode(str, Enum):
    """The response shape a simulated downstream service should produce."""

    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"
    UNKNOWN_AFTER_EFFECT = "unknown_after_effect"


@dataclass(frozen=True, slots=True)
class SimulatedEffect:
    """A durable downstream effect visible to reconciliation."""

    operation_key: str
    operation_type: str
    external_reference: str
    payload: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """The immediate response from a simulated downstream service."""

    status: FailureMode
    external_reference: str | None = None
    error: str | None = None


class SimulatedCompany:
    """Small stateful stand-in for the enterprise systems the agents call."""

    def __init__(self) -> None:
        self._failures: dict[str, FailureMode] = {}
        self._effects: dict[str, SimulatedEffect] = {}
        self._counters: dict[str, int] = {}

    def set_failure(self, operation_type: str, mode: FailureMode) -> None:
        """Configure a deterministic response for an operation type."""

        self._failures[operation_type] = mode

    def submit(
        self,
        *,
        operation_key: str,
        operation_type: str,
        payload: dict[str, JsonValue],
    ) -> SimulationResult:
        """Submit a request, creating at most one effect per operation key."""

        mode = self._failures.get(operation_type, FailureMode.SUCCESS)
        if mode is FailureMode.FAILURE:
            return SimulationResult(
                status=mode,
                error="simulated operation failure",
            )
        if mode is FailureMode.UNKNOWN:
            return SimulationResult(
                status=mode,
                error="simulated timeout before downstream confirmation",
            )

        effect = self._effects.get(operation_key)
        if effect is None:
            next_number = self._counters.get(operation_type, 0) + 1
            self._counters[operation_type] = next_number
            effect = SimulatedEffect(
                operation_key=operation_key,
                operation_type=operation_type,
                external_reference=f"{operation_type}-{next_number}",
                payload=payload,
            )
            self._effects[operation_key] = effect

        if mode is FailureMode.UNKNOWN_AFTER_EFFECT:
            return SimulationResult(
                status=mode,
                error="simulated timeout after downstream effect",
            )
        return SimulationResult(
            status=FailureMode.SUCCESS,
            external_reference=effect.external_reference,
        )

    def reconcile(self, operation_key: str) -> SimulatedEffect | None:
        """Return the effect for an operation without creating another one."""

        return self._effects.get(operation_key)

    def effect_count(self, operation_type: str) -> int:
        """Count durable effects of one operation type."""

        return sum(
            1
            for effect in self._effects.values()
            if effect.operation_type == operation_type
        )


__all__ = [
    "FailureMode",
    "SimulatedCompany",
    "SimulatedEffect",
    "SimulationResult",
]
