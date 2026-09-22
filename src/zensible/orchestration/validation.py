"""Small deterministic validator for specialist task proposals."""

from collections.abc import Iterable
from collections.abc import Set as AbstractSet

from zensible.domain.contracts import ErrorDetail, TaskProposal


def validate_task_proposals(
    proposals: Iterable[TaskProposal],
    *,
    current_revision: int,
    known_task_ids: AbstractSet[str] = frozenset(),
) -> tuple[set[str], list[ErrorDetail]]:
    """Reject stale proposals, unknown dependencies, and dependency cycles."""

    proposal_list = list(proposals)
    proposed_ids = {proposal.task_id for proposal in proposal_list}
    invalid_ids: set[str] = set()
    errors: list[ErrorDetail] = []

    for proposal in proposal_list:
        if proposal.source_revision != current_revision:
            invalid_ids.add(proposal.task_id)
            errors.append(
                ErrorDetail(
                    code="invalid_plan",
                    message=f"{proposal.task_id} was created for a stale state revision",
                )
            )
        unknown_dependencies = (
            set(proposal.depends_on) - proposed_ids - set(known_task_ids)
        )
        if unknown_dependencies:
            invalid_ids.add(proposal.task_id)
            errors.append(
                ErrorDetail(
                    code="invalid_plan",
                    message=(
                        f"{proposal.task_id} references unknown dependencies: "
                        f"{sorted(unknown_dependencies)}"
                    ),
                )
            )

    graph = {
        proposal.task_id: set(proposal.depends_on) & proposed_ids
        for proposal in proposal_list
    }
    visiting: set[str] = set()
    visited: set[str] = set()
    cycle_nodes: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            cycle_nodes.update(visiting)
            return
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in graph.get(task_id, set()):
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in graph:
        visit(task_id)
    if cycle_nodes:
        invalid_ids.update(cycle_nodes)
        errors.append(
            ErrorDetail(
                code="invalid_plan",
                message=f"dependency cycle includes {sorted(cycle_nodes)}",
            )
        )
    return invalid_ids, errors
