"""Errori provider-neutral del Production Planning V1."""

from __future__ import annotations


FROZEN_FAILURE_CATEGORIES = frozenset(
    {
        "PLANNING_INPUT_INVALID",
        "PRODUCTION_KNOWLEDGE_INVALID",
        "PLANNING_INFEASIBLE",
        "ALLOCATION_CONFLICT",
        "CONCURRENCY_CONFLICT",
        "COMMIT_FAILED_ROLLED_BACK",
        "RECONCILIATION_REQUIRED",
        "RUN_FINALIZATION_OUTCOME_UNCERTAIN",
        "INTERNAL_ERROR",
    }
)


class ProductionPlanningError(RuntimeError):
    """Failure applicativa sanitizzata appartenente alla tassonomia congelata."""

    def __init__(self, category: str, code: str, message: str) -> None:
        if category not in FROZEN_FAILURE_CATEGORIES:
            raise ValueError("Categoria Production Planning non congelata.")
        if not _safe_text(code) or not _safe_text(message):
            raise ValueError("Codice e messaggio devono essere testo normalizzato non vuoto.")
        self.category = category
        self.code = code
        self.safe_message = message
        super().__init__(message)


class InvalidProductionPlanningModelError(ProductionPlanningError, ValueError):
    def __init__(self, message: str) -> None:
        super().__init__("PLANNING_INPUT_INVALID", "INVALID_APPLICATION_MODEL", message)


class ProductionPlanningOutcomeUncertain(ProductionPlanningError):
    def __init__(self, message: str = "Esito del commit non determinabile.") -> None:
        super().__init__("RECONCILIATION_REQUIRED", "COMMIT_OUTCOME_UNCERTAIN", message)


class ProductionPlanningRunFinalizationOutcomeUncertain(ProductionPlanningError):
    def __init__(
        self,
        *,
        attempted_operation: str,
        original_error: ProductionPlanningError,
        planning_run_public_id: object,
        correlation_id: str,
    ) -> None:
        if attempted_operation not in {"FINALIZE_FAILURE", "REQUIRE_RECONCILIATION"}:
            raise ValueError("Operazione di finalizzazione non congelata.")
        self.attempted_operation = attempted_operation
        self.original_failure_category = original_error.category
        self.original_code = original_error.code
        self.original_safe_message = original_error.safe_message
        self.planning_run_public_id = planning_run_public_id
        self.correlation_id = correlation_id
        super().__init__(
            "RUN_FINALIZATION_OUTCOME_UNCERTAIN",
            "RUN_FINALIZATION_OUTCOME_UNCERTAIN",
            "Esito della finalizzazione RUN non determinabile; è richiesta review operativa.",
        )


def _safe_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()
