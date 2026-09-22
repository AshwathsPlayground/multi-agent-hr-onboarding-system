from zensible.persistence.postgres import checkpoint_serializer
from zensible.simulation import SimulatedCompany
from zensible.tools.operation_executor import OperationExecutor, OperationRequest


def test_checkpoint_serializer_round_trips_operation_result() -> None:
    executor = OperationExecutor(SimulatedCompany())
    result = executor.execute(
        OperationRequest(
            operation_key="onb_123:payroll:setup",
            task_id="task_payroll",
            operation_type="submit_payroll_setup",
            payload={"employee_id": "emp_123"},
        )
    )

    serializer = checkpoint_serializer()
    encoded = serializer.dumps_typed({"action_result": result})
    restored = serializer.loads_typed(encoded)

    assert restored["action_result"].status is result.status
    assert restored["action_result"].operation.external_reference == (
        "submit_payroll_setup-1"
    )
