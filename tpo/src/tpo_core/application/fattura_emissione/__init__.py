"""API applicativa del boundary FATTURA_EMISSIONE."""

from .errors import (
    FatturaCommitError,
    FatturaCommitOutcomeUncertain,
    FatturaConcurrencyError,
    FatturaEmissioneError,
    FatturaIdempotencyConflictError,
    FatturaReconciliationRequiredError,
    FatturaValidationError,
    InvalidEmitFatturaCommandError,
)
from .models import EmitFattura, EmitFatturaAuthority, EmitFatturaResult
from .ports import FatturaEmissioneWriter
from .service import FatturaEmissioneService

__all__ = [
    "EmitFattura", "EmitFatturaAuthority", "EmitFatturaResult",
    "FatturaCommitError", "FatturaCommitOutcomeUncertain", "FatturaConcurrencyError",
    "FatturaEmissioneError", "FatturaEmissioneService", "FatturaEmissioneWriter",
    "FatturaIdempotencyConflictError", "FatturaReconciliationRequiredError",
    "FatturaValidationError", "InvalidEmitFatturaCommandError",
]
