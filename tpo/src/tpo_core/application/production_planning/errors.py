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


def _safe_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()
