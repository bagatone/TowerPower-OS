"""Porte provider-neutral congelate del Production Planning V1."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .errors import ProductionPlanningError
from .models import (
    ProductionPlanningLoadedInput,
    PolicyVersionReference,
    ProductionPlanningCommand,
    ProductionPlanningCommit,
    ProductionPlanningReconciliationRequiredResult,
    ProductionPlanningResult,
    ProductionPlanningRunSnapshot,
    PublicId,
    RunMessage,
)


class IdentityAllocationPort(Protocol):
    def allocate(self, sequence_name: str) -> PublicId: ...


class ProductionPlanningInputPort(Protocol):
    def load(self, command: ProductionPlanningCommand) -> ProductionPlanningLoadedInput: ...


class ProductionPlanningRunPort(Protocol):
    def open(
        self,
        *,
        public_id: PublicId,
        policy: PolicyVersionReference,
        business_at: datetime,
        started_at: datetime,
        created_by: str,
    ) -> ProductionPlanningRunSnapshot: ...

    def finalize_failure(
        self,
        *,
        run: ProductionPlanningRunSnapshot,
        completed_at: datetime,
        error: ProductionPlanningError,
        messages: tuple[RunMessage, ...],
    ) -> None: ...

    def require_reconciliation(
        self,
        *,
        run: ProductionPlanningRunSnapshot,
        business_at: datetime,
        observed_at: datetime,
        correlation_id: str,
        error: ProductionPlanningError,
    ) -> ProductionPlanningReconciliationRequiredResult: ...


class ProductionPlanningCommitPort(Protocol):
    def commit(
        self, write_set: ProductionPlanningCommit, *, completed_at: datetime
    ) -> ProductionPlanningResult: ...


class PlanningClockPort(Protocol):
    def now(self) -> datetime: ...
