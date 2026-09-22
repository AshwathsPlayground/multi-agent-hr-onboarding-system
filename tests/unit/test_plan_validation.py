from zensible.domain.contracts import AgentName, ErrorDetail, TaskIntent, TaskProposal
from zensible.orchestration.validation import validate_task_proposals


def proposal(
    task_id: str,
    *,
    source_revision: int = 0,
    depends_on: list[str] | None = None,
) -> TaskProposal:
    return TaskProposal(
        task_id=task_id,
        owner_agent=AgentName.IT,
        intent=TaskIntent.SUBMIT_IT_REQUEST,
        goal=task_id,
        source_revision=source_revision,
        depends_on=depends_on or [],
    )


def test_rejects_proposals_from_an_old_state_revision() -> None:
    invalid, errors = validate_task_proposals(
        [proposal("task_1", source_revision=1)], current_revision=2
    )

    assert invalid == {"task_1"}
    assert [error.code for error in errors] == ["invalid_plan"]


def test_rejects_unknown_dependencies_and_cycles() -> None:
    invalid, errors = validate_task_proposals(
        [
            proposal("task_1", depends_on=["missing"]),
            proposal("task_2", depends_on=["task_3"]),
            proposal("task_3", depends_on=["task_2"]),
        ],
        current_revision=0,
    )

    assert invalid == {"task_1", "task_2", "task_3"}
    assert all(isinstance(error, ErrorDetail) for error in errors)
    assert len(errors) == 2


def test_accepts_dependencies_that_are_known_or_proposed() -> None:
    invalid, errors = validate_task_proposals(
        [proposal("task_2", depends_on=["task_1"])],
        current_revision=0,
        known_task_ids={"task_1"},
    )

    assert invalid == set()
    assert errors == []
