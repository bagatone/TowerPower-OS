"""Boundary applicativo ORDINE_MANUALE V1."""

from .errors import (
    InvalidOrdineManualeCommandError,
    OrdineManualeClienteNotFoundError,
    OrdineManualeCommitOutcomeUncertainError,
    OrdineManualeCommitRolledBackError,
    OrdineManualeError,
    OrdineManualeIdempotencyConflictError,
    OrdineManualeIdentityUnavailableError,
    OrdineManualePersistenceInvariantError,
    OrdineManualeReconciliationRequiredError,
    OrdineManualeVarietaError,
)
from .models import (
    OrdineManualeAuthority,
    RegistraOrdineManuale,
    RegistraOrdineManualeResult,
    RigaOrdineManuale,
    RigaOrdineRegistrata,
)
from .ports import OrdineManualeWriter
from .service import OrdineManualeService

__all__ = [
    "InvalidOrdineManualeCommandError",
    "OrdineManualeAuthority",
    "OrdineManualeClienteNotFoundError",
    "OrdineManualeCommitOutcomeUncertainError",
    "OrdineManualeCommitRolledBackError",
    "OrdineManualeError",
    "OrdineManualeIdempotencyConflictError",
    "OrdineManualeIdentityUnavailableError",
    "OrdineManualePersistenceInvariantError",
    "OrdineManualeReconciliationRequiredError",
    "OrdineManualeService",
    "OrdineManualeVarietaError",
    "OrdineManualeWriter",
    "RegistraOrdineManuale",
    "RegistraOrdineManualeResult",
    "RigaOrdineManuale",
    "RigaOrdineRegistrata",
]
