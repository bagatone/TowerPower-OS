"""Boundary applicativo MOVIMENTO_ARTICOLO V1 (RegistraMovimentoArticolo)."""

from .errors import (
    InvalidMovimentoArticoloCommandError,
    MovimentoArticoloArticoloNotFoundError,
    MovimentoArticoloCommitOutcomeUncertainError,
    MovimentoArticoloCommitRolledBackError,
    MovimentoArticoloConcurrencyError,
    MovimentoArticoloError,
    MovimentoArticoloIdempotencyConflictError,
    MovimentoArticoloIdentityUnavailableError,
    MovimentoArticoloInsufficientStockError,
    MovimentoArticoloPersistenceInvariantError,
    MovimentoArticoloReconciliationRequiredError,
    MovimentoArticoloStockUnitMismatchError,
)
from .models import (
    MovimentoArticoloAuthority,
    RegistraMovimentoArticolo,
    RegistraMovimentoArticoloResult,
)
from .ports import MovimentoArticoloWriter
from .service import MovimentoArticoloService

__all__ = [
    "InvalidMovimentoArticoloCommandError",
    "MovimentoArticoloArticoloNotFoundError",
    "MovimentoArticoloAuthority",
    "MovimentoArticoloCommitOutcomeUncertainError",
    "MovimentoArticoloCommitRolledBackError",
    "MovimentoArticoloConcurrencyError",
    "MovimentoArticoloError",
    "MovimentoArticoloIdempotencyConflictError",
    "MovimentoArticoloIdentityUnavailableError",
    "MovimentoArticoloInsufficientStockError",
    "MovimentoArticoloPersistenceInvariantError",
    "MovimentoArticoloReconciliationRequiredError",
    "MovimentoArticoloService",
    "MovimentoArticoloStockUnitMismatchError",
    "MovimentoArticoloWriter",
    "RegistraMovimentoArticolo",
    "RegistraMovimentoArticoloResult",
]
