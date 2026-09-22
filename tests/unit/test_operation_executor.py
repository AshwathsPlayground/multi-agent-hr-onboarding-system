import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from zensible.domain.contracts import OperationStatus, ReconciliationStatus
from zensible.simulation.fixtures import FailureMode, SimulatedCompany
from zensible.tools.operation_executor import (
    OperationExecutor,
    OperationFingerprintConflict,
    OperationRequest,
)


def payroll_request(*, amount: str = "150000.00") -> OperationRequest:
    return OperationRequest(
        operation_key="onb_123:task_payroll:submit_payroll_setup:2",
        task_id="task_payroll",
        operation_type="submit_payroll_setup",
        payload={"employee_id": "emp_123", "amount": amount, "currency": "INR"},
    )


def test_first_operation_succeeds_and_records_one_effect() -> None:
    company = SimulatedCompany()
    executor = OperationExecutor(company)

    result = executor.execute(payroll_request())

    assert result.status is OperationStatus.SUCCEEDED
    assert result.replayed is False
    assert result.operation.external_reference == "submit_payroll_setup-1"
    assert result.operation.reconciliation_status is ReconciliationStatus.NOT_REQUIRED
    assert company.effect_count("submit_payroll_setup") == 1


def test_replaying_same_request_returns_existing_success_without_new_effect() -> None:
    company = SimulatedCompany()
    executor = OperationExecutor(company)
    request = payroll_request()

    first = executor.execute(request)
    replay = executor.execute(request)

    assert first.status is OperationStatus.SUCCEEDED
    assert replay.status is OperationStatus.SUCCEEDED
    assert replay.replayed is True
    assert replay.operation.attempts == 1
    assert replay.operation.external_reference == first.operation.external_reference
    assert company.effect_count("submit_payroll_setup") == 1


def test_changed_fingerprint_for_existing_operation_is_a_conflict() -> None:
    company = SimulatedCompany()
    executor = OperationExecutor(company)
    executor.execute(payroll_request())

    with pytest.raises(OperationFingerprintConflict):
        executor.execute(payroll_request(amount="175000.00"))

    assert company.effect_count("submit_payroll_setup") == 1


def test_deterministic_failure_is_preserved_without_an_effect() -> None:
    company = SimulatedCompany()
    company.set_failure("submit_it_request", FailureMode.FAILURE)
    executor = OperationExecutor(company)

    result = executor.execute(
        OperationRequest(
            operation_key="onb_123:task_it:submit_it_request:2",
            task_id="task_it",
            operation_type="submit_it_request",
            payload={"employee_id": "emp_123", "resource": "laptop"},
        )
    )

    assert result.status is OperationStatus.FAILED
    assert result.operation.attempts == 1
    assert result.operation.last_error == "simulated operation failure"
    assert company.effect_count("submit_it_request") == 0


def test_unknown_after_write_is_reconciled_without_duplicate_effect() -> None:
    company = SimulatedCompany()
    company.set_failure("submit_payroll_setup", FailureMode.UNKNOWN_AFTER_EFFECT)
    executor = OperationExecutor(company)
    request = payroll_request()

    uncertain = executor.execute(request)
    reconciled = executor.execute(request)

    assert uncertain.status is OperationStatus.UNKNOWN
    assert uncertain.operation.reconciliation_status is ReconciliationStatus.NOT_STARTED
    assert reconciled.status is OperationStatus.SUCCEEDED
    assert reconciled.replayed is False
    assert reconciled.operation.reconciliation_status is ReconciliationStatus.FOUND
    assert reconciled.operation.external_reference == "submit_payroll_setup-1"
    assert company.effect_count("submit_payroll_setup") == 1


def test_unknown_without_effect_remains_uncertain_and_can_be_reconciled_later() -> None:
    company = SimulatedCompany()
    company.set_failure("deliver_notification", FailureMode.UNKNOWN)
    executor = OperationExecutor(company)
    request = OperationRequest(
        operation_key="onb_123:task_notify:deliver_notification:2",
        task_id="task_notify",
        operation_type="deliver_notification",
        payload={"recipient": "employee:emp_123", "template": "welcome"},
    )

    uncertain = executor.execute(request)
    assert uncertain.status is OperationStatus.UNKNOWN

    company.set_failure("deliver_notification", FailureMode.SUCCESS)
    still_uncertain = executor.reconcile(request.operation_key)

    assert still_uncertain.status is OperationStatus.UNKNOWN
    assert (
        still_uncertain.operation.reconciliation_status
        is ReconciliationStatus.NOT_FOUND
    )
    assert company.effect_count("deliver_notification") == 0


def test_restoring_checkpointed_operation_preserves_replay_protection() -> None:
    company = SimulatedCompany()
    original = OperationExecutor(company)
    request = payroll_request()
    first = original.execute(request)

    resumed = OperationExecutor(company)
    resumed.restore([first.operation])
    replay = resumed.execute(request)

    assert replay.replayed is True
    assert company.effect_count("submit_payroll_setup") == 1
