"""Boundary applicativo FATTURA_RETTIFICA V1 (RectifyFattura)."""

from .errors import (
    FatturaRettificaCommitError,
    FatturaRettificaCommitOutcomeUncertain,
    FatturaRettificaConcurrencyError,
    FatturaRettificaError,
    FatturaRettificaIdempotencyConflictError,
    FatturaRettificaReconciliationRequiredError,
    FatturaRettificaValidationError,
    InvalidRectifyFatturaCommandError,
)
from .models import (
    RectifyFattura,
    RectifyFatturaAuthority,
    RectifyFatturaResult,
    RettificaRigaFattura,
)
from .ports import FatturaRettificaWriter
from .service import FatturaRettificaService

__all__ = [
    "FatturaRettificaCommitError",
    "FatturaRettificaCommitOutcomeUncertain",
    "FatturaRettificaConcurrencyError",
    "FatturaRettificaError",
    "FatturaRettificaIdempotencyConflictError",
    "FatturaRettificaReconciliationRequiredError",
    "FatturaRettificaService",
    "FatturaRettificaValidationError",
    "FatturaRettificaWriter",
    "InvalidRectifyFatturaCommandError",
    "RectifyFattura",
    "RectifyFatturaAuthority",
    "RectifyFatturaResult",
    "RettificaRigaFattura",
]
