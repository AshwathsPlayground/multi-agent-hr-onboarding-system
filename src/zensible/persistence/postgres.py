"""PostgreSQL checkpointer lifecycle for LangGraph."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from zensible.domain.contracts import (
    AgentContext,
    AgentName,
    ComplianceAssessment,
    ComplianceRequirement,
    ComplianceRequirementStatus,
    Conflict,
    DeliveryResult,
    DeliveryStatus,
    Effect,
    ErrorDetail,
    Finding,
    FindingSeverity,
    MissingInput,
    ModelAssessment,
    OnboardingRequest,
    OnboardingStatus,
    OperationRecord,
    OperationStatus,
    PayrollAssessment,
    Provenance,
    ProvisioningAssessment,
    ProvisioningItem,
    ReconciliationStatus,
    RequirementCode,
    ResumeEvent,
    ResumeEventKind,
    SpecialistOutcome,
    SpecialistPhase,
    SpecialistResult,
    TaskIntent,
    TaskProposal,
    TaskRecord,
    TaskStatus,
    ValidatedEmployeeFacts,
)

CHECKPOINT_TYPES = (
    AgentContext,
    AgentName,
    ComplianceAssessment,
    ComplianceRequirement,
    ComplianceRequirementStatus,
    Conflict,
    DeliveryResult,
    DeliveryStatus,
    Effect,
    ErrorDetail,
    Finding,
    FindingSeverity,
    MissingInput,
    ModelAssessment,
    OnboardingRequest,
    OnboardingStatus,
    OperationRecord,
    OperationStatus,
    PayrollAssessment,
    Provenance,
    ProvisioningAssessment,
    ProvisioningItem,
    ReconciliationStatus,
    RequirementCode,
    ResumeEvent,
    ResumeEventKind,
    SpecialistOutcome,
    SpecialistPhase,
    SpecialistResult,
    TaskIntent,
    TaskProposal,
    TaskRecord,
    TaskStatus,
    ValidatedEmployeeFacts,
)


def checkpoint_serializer() -> JsonPlusSerializer:
    """Use a narrow allowlist when deserializing graph state from PostgreSQL."""

    return JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_TYPES)


@asynccontextmanager
async def postgres_checkpointer(
    dsn: str,
    *,
    setup: bool = False,
) -> AsyncIterator[AsyncPostgresSaver]:
    """Yield a LangGraph PostgreSQL saver and optionally initialize its tables."""

    async with AsyncPostgresSaver.from_conn_string(
        dsn, serde=checkpoint_serializer()
    ) as saver:
        if setup:
            await saver.setup()
        yield saver
