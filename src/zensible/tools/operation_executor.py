"""Idempotent operation seam shared by specialist action subgraphs."""

import json
from collections.abc import Iterable
from hashlib import sha256
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from zensible.domain.contracts import (
    OperationRecord,
    OperationStatus,
    ReconciliationStatus,
)
from zensible.simulation.fixtures import FailureMode, SimulatedCompany


class OperationRequest(BaseModel):
    """Stable input for one logical side effect."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_key: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    operation_type: str = Field(min_length=1)
    payload: dict[str, JsonValue]

    @property
    def fingerprint(self) -> str:
        canonical = json.dumps(
            {
                "operation_type": self.operation_type,
                "payload": self.payload,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(canonical.encode("utf-8")).hexdigest()


class OperationResult(BaseModel):
    """Public result that distinguishes an execution from a replay."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: OperationStatus
    operation: OperationRecord
    replayed: bool = False


class OperationFingerprintConflict(ValueError):
    """Raised when one operation key is reused for a different request."""


class OperationExecutor:
    """Own execution, replay protection, and reconciliation for writes."""

    def __init__(self, company: SimulatedCompany) -> None:
        self._company = company
        self._records: dict[str, OperationRecord] = {}
        self._lock_guard = RLock()
        self._operation_locks: dict[str, RLock] = {}

    def _lock_for(self, operation_key: str) -> RLock:
        with self._lock_guard:
            return self._operation_locks.setdefault(operation_key, RLock())

    def execute(self, request: OperationRequest) -> OperationResult:
        with self._lock_for(request.operation_key):
            return self._execute_locked(request)

    def _execute_locked(self, request: OperationRequest) -> OperationResult:
        """Execute once, reconcile unknowns, or return an equivalent replay."""

        existing = self._records.get(request.operation_key)
        if existing is not None:
            if existing.request_fingerprint != request.fingerprint:
                raise OperationFingerprintConflict(
                    f"operation key {request.operation_key!r} has a different request fingerprint"
                )
            if existing.status is OperationStatus.UNKNOWN:
                return self.reconcile(request.operation_key)
            return OperationResult(
                status=existing.status, operation=existing, replayed=True
            )

        in_flight = OperationRecord(
            operation_key=request.operation_key,
            task_id=request.task_id,
            operation_type=request.operation_type,
            request_fingerprint=request.fingerprint,
            status=OperationStatus.IN_FLIGHT,
            attempts=1,
        )
        outcome = self._company.submit(
            operation_key=request.operation_key,
            operation_type=request.operation_type,
            payload=request.payload,
        )
        if outcome.status is FailureMode.SUCCESS:
            status = OperationStatus.SUCCEEDED
            reference = outcome.external_reference
            error = None
            reconciliation_status = ReconciliationStatus.NOT_REQUIRED
        elif outcome.status is FailureMode.FAILURE:
            status = OperationStatus.FAILED
            reference = None
            error = outcome.error
            reconciliation_status = ReconciliationStatus.NOT_REQUIRED
        else:
            status = OperationStatus.UNKNOWN
            reference = None
            error = outcome.error
            reconciliation_status = ReconciliationStatus.NOT_STARTED

        record = in_flight.model_copy(
            update={
                "status": status,
                "external_reference": reference,
                "last_error": error,
                "reconciliation_status": reconciliation_status,
            }
        )
        self._records[request.operation_key] = record
        return OperationResult(status=status, operation=record)

    def reconcile(self, operation_key: str) -> OperationResult:
        with self._lock_for(operation_key):
            return self._reconcile_locked(operation_key)

    def _reconcile_locked(self, operation_key: str) -> OperationResult:
        """Resolve an unknown operation using the downstream system's view."""

        record = self._records[operation_key]
        if record.status is not OperationStatus.UNKNOWN:
            return OperationResult(
                status=record.status, operation=record, replayed=True
            )

        effect = self._company.reconcile(operation_key)
        if effect is not None:
            status = OperationStatus.SUCCEEDED
            error = None
            reconciliation_status = ReconciliationStatus.FOUND
            reference = effect.external_reference
        else:
            status = OperationStatus.UNKNOWN
            error = "operation was not found during reconciliation"
            reconciliation_status = ReconciliationStatus.NOT_FOUND
            reference = None

        reconciled = record.model_copy(
            update={
                "status": status,
                "external_reference": reference,
                "last_error": error,
                "reconciliation_status": reconciliation_status,
            }
        )
        self._records[operation_key] = reconciled
        return OperationResult(status=reconciled.status, operation=reconciled)

    def get(self, operation_key: str) -> OperationRecord | None:
        """Read the current record without executing anything."""

        with self._lock_for(operation_key):
            return self._records.get(operation_key)

    def restore(self, records: Iterable[OperationRecord]) -> None:
        """Hydrate records recovered from a graph checkpoint before resuming."""

        for record in records:
            with self._lock_for(record.operation_key):
                existing = self._records.get(record.operation_key)
                if (
                    existing is not None
                    and existing.request_fingerprint != record.request_fingerprint
                ):
                    raise OperationFingerprintConflict(record.operation_key)
                self._records[record.operation_key] = record
