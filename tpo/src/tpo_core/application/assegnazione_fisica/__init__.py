"""Boundary applicativo ASSEGNAZIONE_FISICA V1 (RegistraAssegnazioneFisica)."""

from .errors import (
    AssegnazioneFisicaCommitOutcomeUncertainError,
    AssegnazioneFisicaCommitRolledBackError,
    AssegnazioneFisicaConsegnaNotFoundError,
    AssegnazioneFisicaConsegnaRigaOrdineMismatchError,
    AssegnazioneFisicaError,
    AssegnazioneFisicaIdempotencyConflictError,
    AssegnazioneFisicaIdentityUnavailableError,
    AssegnazioneFisicaPersistenceInvariantError,
    AssegnazioneFisicaRaccoltaNotFoundError,
    AssegnazioneFisicaReconciliationRequiredError,
    AssegnazioneFisicaRigaOrdineNotFoundError,
    InvalidAssegnazioneFisicaCommandError,
)
from .models import (
    AssegnazioneFisicaAuthority,
    RegistraAssegnazioneFisica,
    RegistraAssegnazioneFisicaResult,
)
from .ports import AssegnazioneFisicaWriter
from .service import AssegnazioneFisicaService

__all__ = [
    "AssegnazioneFisicaAuthority",
    "AssegnazioneFisicaCommitOutcomeUncertainError",
    "AssegnazioneFisicaCommitRolledBackError",
    "AssegnazioneFisicaConsegnaNotFoundError",
    "AssegnazioneFisicaConsegnaRigaOrdineMismatchError",
    "AssegnazioneFisicaError",
    "AssegnazioneFisicaIdempotencyConflictError",
    "AssegnazioneFisicaIdentityUnavailableError",
    "AssegnazioneFisicaPersistenceInvariantError",
    "AssegnazioneFisicaRaccoltaNotFoundError",
    "AssegnazioneFisicaReconciliationRequiredError",
    "AssegnazioneFisicaRigaOrdineNotFoundError",
    "AssegnazioneFisicaService",
    "AssegnazioneFisicaWriter",
    "InvalidAssegnazioneFisicaCommandError",
    "RegistraAssegnazioneFisica",
    "RegistraAssegnazioneFisicaResult",
]
