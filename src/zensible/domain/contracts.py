"""Stable, serializable contracts shared by the onboarding graph and agents."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ContractModel(BaseModel):
    """Base configuration shared by models crossing graph or agent boundaries."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class AgentName(str, Enum):
    HR = "hr"
    IT = "it"
    COMPLIANCE = "compliance"
    PAYROLL = "payroll"
    COMMUNICATION = "communication"


class SpecialistPhase(str, Enum):
    ASSESSMENT = "assessment"
    ACTION = "action"


class SpecialistOutcome(str, Enum):
    COMPLETED = "completed"
    NEEDS_INPUT = "needs_input"
    NEEDS_RESOLUTION = "needs_resolution"
    REQUIRES_REASSESSMENT = "requires_reassessment"
    FAILED = "failed"


class AgentDecision(str, Enum):
    """Bounded model guidance that the deterministic agent can safely apply."""

    PROCEED = "proceed"
    REQUEST_INPUT = "request_input"
    ESCALATE = "escalate"


class OnboardingStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    WAITING_FOR_INPUT = "waiting_for_input"
    WAITING_FOR_EXTERNAL_EVENT = "waiting_for_external_event"
    NEEDS_RESOLUTION = "needs_resolution"
    BLOCKED_BY_FAILURE = "blocked_by_failure"
    INVALID_PLAN = "invalid_plan"
    NO_PROGRESS = "no_progress"


class TaskIntent(str, Enum):
    VALIDATE_HR_FACTS = "validate_hr_facts"
    CREATE_COMPLIANCE_CASE = "create_compliance_case"
    VERIFY_SECURITY_TRAINING = "verify_security_training"
    SUBMIT_IT_REQUEST = "submit_it_request"
    SUBMIT_PAYROLL_SETUP = "submit_payroll_setup"
    DELIVER_NOTIFICATION = "deliver_notification"


class TaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    WAITING = "waiting"
    BLOCKED = "blocked"
    FAILED = "failed"
    UNKNOWN = "unknown"
    NEEDS_RESOLUTION = "needs_resolution"
    STALE = "stale"


class RequirementCode(str, Enum):
    EMPLOYEE_IDENTITY_RESOLVED = "employee_identity_resolved"
    HR_FACTS_VALIDATED = "hr_facts_validated"
    SECURITY_TRAINING_VERIFIED = "security_training_verified"
    BANK_DETAILS_VALIDATED = "bank_details_validated"
    COMPENSATION_VALIDATED = "compensation_validated"
    COMPLIANCE_CASE_OPENED = "compliance_case_opened"


class OperationStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_FLIGHT = "in_flight"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    NEEDS_RESOLUTION = "needs_resolution"


class ReconciliationStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    NOT_STARTED = "not_started"
    FOUND = "found"
    NOT_FOUND = "not_found"
    UNCERTAIN = "uncertain"


class ResumeEventKind(str, Enum):
    EMPLOYEE_FACT_CORRECTION = "employee_fact_correction"
    BANK_DETAILS_SUBMITTED = "bank_details_submitted"
    TRAINING_EVIDENCE_SUBMITTED = "training_evidence_submitted"
    COMPLIANCE_STATUS_UPDATE = "compliance_status_update"
    CONFLICT_RESOLUTION = "conflict_resolution"
    NOTIFICATION_RETRY = "notification_retry"


class FindingSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ComplianceRequirementStatus(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    MISSING = "missing"
    PENDING = "pending"
    VERIFIED = "verified"
    EXPIRED = "expired"
    REVIEW_REQUIRED = "review_required"


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    UNKNOWN = "unknown"
    NEEDS_RESOLUTION = "needs_resolution"


class Provenance(ContractModel):
    source: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    observed_at: datetime | None = None


class Finding(ContractModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: FindingSeverity = FindingSeverity.INFO


class MissingInput(ContractModel):
    field: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    requested_from: str | None = None


class Conflict(ContractModel):
    field: str = Field(min_length=1)
    values: dict[str, JsonValue] = Field(min_length=2)
    resolution_required: bool = True


class Effect(ContractModel):
    effect_type: str = Field(min_length=1)
    reference: str | None = None
    status: str = Field(min_length=1)


class NotificationNeed(ContractModel):
    kind: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    recipient_references: list[str] = Field(default_factory=list)


class ErrorDetail(ContractModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool = False


class OnboardingRequest(ContractModel):
    onboarding_id: str = Field(min_length=1)
    employee_reference: str = Field(min_length=1)
    requested_role: str = Field(min_length=1)
    requested_location: str = Field(min_length=1)
    requested_joining_date: date
    requested_by: str = Field(min_length=1)


class ValidatedEmployeeFacts(ContractModel):
    employee_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    location: str = Field(min_length=1)
    joining_date: date
    manager_id: str | None = None
    department: str | None = None
    provenance: dict[str, list[Provenance]] = Field(default_factory=dict)


class TaskProposal(ContractModel):
    task_id: str = Field(min_length=1)
    owner_agent: AgentName
    intent: TaskIntent
    goal: str = Field(min_length=1)
    source_revision: int = Field(ge=0)
    depends_on: list[str] = Field(default_factory=list)
    required_requirements: list[RequirementCode] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    input_reference: str | None = None
    operation_key: str | None = None


class TaskRecord(TaskProposal):
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = Field(default=0, ge=0)
    result_reference: str | None = None
    block_reason: str | None = None


class OperationRecord(ContractModel):
    operation_key: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    operation_type: str = Field(min_length=1)
    request_fingerprint: str = Field(min_length=1)
    status: OperationStatus = OperationStatus.NOT_STARTED
    attempts: int = Field(default=0, ge=0)
    external_reference: str | None = None
    last_error: str | None = None
    reconciliation_status: ReconciliationStatus = ReconciliationStatus.NOT_REQUIRED


class ResumeEvent(ContractModel):
    kind: ResumeEventKind
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    source: str = Field(min_length=1)
    submitted_at: datetime


class AgentContext(ContractModel):
    onboarding_id: str = Field(min_length=1)
    state_revision: int = Field(ge=0)
    facts_version: int = Field(ge=0)
    policy_version: str = Field(min_length=1)
    validated_hr_facts: ValidatedEmployeeFacts | None = None
    relevant_findings: dict[str, list[Finding]] = Field(default_factory=dict)
    existing_tasks: list[TaskRecord] = Field(default_factory=list)
    existing_operations: list[OperationRecord] = Field(default_factory=list)
    resume_event: ResumeEvent | None = None


class ComplianceRequirement(ContractModel):
    code: RequirementCode
    status: ComplianceRequirementStatus
    evidence_references: list[str] = Field(default_factory=list)


class ComplianceAssessment(ContractModel):
    requirements: list[ComplianceRequirement] = Field(default_factory=list)
    case_reference: str | None = None
    review_reasons: list[str] = Field(default_factory=list)


class ProvisioningItem(ContractModel):
    resource: str = Field(min_length=1)
    status: TaskStatus = TaskStatus.PENDING
    required_requirements: list[RequirementCode] = Field(default_factory=list)
    existing_reference: str | None = None


class ProvisioningAssessment(ContractModel):
    items: list[ProvisioningItem] = Field(default_factory=list)
    request_references: list[str] = Field(default_factory=list)


class PayrollAssessment(ContractModel):
    compensation_reference: str | None = None
    bank_details_reference: str | None = None
    salary: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None
    pay_schedule: str | None = None
    effective_date: date | None = None
    eligible: bool = False


class DeliveryResult(ContractModel):
    status: DeliveryStatus
    recipient_references: list[str] = Field(default_factory=list)
    notification_reference: str | None = None


class ModelAssessment(ContractModel):
    """Structured model guidance consumed by a specialist and its parent graph."""

    summary: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    decision: AgentDecision = AgentDecision.PROCEED
    # None means the model did not choose among the agent's candidates. An
    # explicit list is validated against those candidates before it can affect
    # task planning.
    approved_task_ids: list[str] | None = None
    requested_inputs: list[MissingInput] = Field(default_factory=list)
    escalation_reasons: list[str] = Field(default_factory=list)


PayloadT = TypeVar("PayloadT")


class SpecialistResult[PayloadT](ContractModel):
    agent: AgentName
    phase: SpecialistPhase
    outcome: SpecialistOutcome
    state_revision: int = Field(ge=0)
    payload: PayloadT | None = None
    findings: list[Finding] = Field(default_factory=list)
    missing_inputs: list[MissingInput] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    proposed_tasks: list[TaskProposal] = Field(default_factory=list)
    effects: list[Effect] = Field(default_factory=list)
    notification_needs: list[NotificationNeed] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)
    reassessment_reasons: list[str] = Field(default_factory=list)
    model_output: ModelAssessment | None = None


__all__ = [
    "AgentContext",
    "AgentDecision",
    "AgentName",
    "ComplianceAssessment",
    "ComplianceRequirement",
    "ComplianceRequirementStatus",
    "Conflict",
    "DeliveryResult",
    "DeliveryStatus",
    "Effect",
    "ErrorDetail",
    "Finding",
    "FindingSeverity",
    "MissingInput",
    "ModelAssessment",
    "OnboardingRequest",
    "OnboardingStatus",
    "OperationRecord",
    "OperationStatus",
    "PayrollAssessment",
    "Provenance",
    "ProvisioningAssessment",
    "ProvisioningItem",
    "ReconciliationStatus",
    "RequirementCode",
    "ResumeEvent",
    "ResumeEventKind",
    "SpecialistOutcome",
    "SpecialistPhase",
    "SpecialistResult",
    "TaskIntent",
    "TaskProposal",
    "TaskRecord",
    "TaskStatus",
    "ValidatedEmployeeFacts",
]
