import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from zensible import observability


def test_disabled_tracing_preserves_sync_callable_and_never_needs_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)

    @observability.trace_operation("hr.validate")
    def validate(value: str) -> str:
        return value.upper()

    assert observability.tracing_enabled() is False
    assert validate("employee") == "EMPLOYEE"


@pytest.mark.asyncio
async def test_disabled_tracing_preserves_async_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("LANGCHAIN_API_KEY", "not-used-offline")

    @observability.trace_operation("payroll.assess")
    async def assess(value: int) -> int:
        return value + 1

    assert await assess(41) == 42


def test_enabled_tracing_delegates_native_configuration_and_preserves_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_traceable(**kwargs: Any):
        captured.update(kwargs)

        def decorate(function):
            def traced(*args: Any, **kwargs: Any) -> Any:
                return function(*args, **kwargs)

            return traced

        return decorate

    monkeypatch.setattr(observability, "traceable", fake_traceable)

    @observability.trace_operation(
        "it.provision",
        metadata={"agent": "it"},
        tags=("onboarding", "it"),
        run_type="tool",
        enabled=True,
    )
    def provision(employee_id: str) -> dict[str, str]:
        return {"employee_id": employee_id, "status": "submitted"}

    assert provision("emp_123") == {
        "employee_id": "emp_123",
        "status": "submitted",
    }
    assert captured == {
        "name": "it.provision",
        "run_type": "tool",
        "metadata": {"agent": "it"},
        "tags": ["onboarding", "it"],
    }


def test_empty_operation_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="operation_name"):
        observability.trace_operation("   ")


def test_human_event_format_summarizes_context_and_keeps_agent_output_visible() -> None:
    request = observability.ExecutionEvent(
        kind="model.request",
        name="payroll",
        payload={
            "provider": "live",
            "input": (
                '{"onboarding_id":"onb_123", "state_revision":1, '
                '"validated_hr_facts":{"employee_id":"emp_123"}, '
                '"existing_tasks":[], "existing_operations":[]}'
            ),
        },
    )
    result = observability.ExecutionEvent(
        kind="agent.result",
        name="payroll",
        payload={
            "result": {
                "outcome": "completed",
                "phase": "assessment",
                "state_revision": 1,
                "model_output": {
                    "summary": "model assessed payroll readiness",
                    "confidence": 0.92,
                },
                "missing_inputs": [
                    {"field": "bank_details_reference", "reason": "required"}
                ],
                "payload": {"eligible": False, "compensation_reference": "comp_123"},
            }
        },
    )

    rendered = observability.render_events([request, result])

    assert "provider=live" in rendered
    assert "onboarding_id=onb_123" in rendered
    assert "employee_id=emp_123" in rendered
    assert "model assessed payroll readiness" in rendered
    assert "Missing input: bank_details_reference — required" in rendered
    assert "validated_hr_facts" not in rendered
