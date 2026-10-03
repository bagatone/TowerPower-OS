"""Boundary applicativo RETTIFICA_GIACENZA V1."""

from .errors import (
    InvalidRettificaGiacenzaCommandError,
    RettificaGiacenzaCommitOutcomeUncertainError,
    RettificaGiacenzaCommitRolledBackError,
    RettificaGiacenzaConcurrencyError,
    RettificaGiacenzaError,
    RettificaGiacenzaIdempotencyConflictError,
    RettificaGiacenzaIdentityUnavailableError,
    RettificaGiacenzaOrigineError,
    RettificaGiacenzaPersistenceInvariantError,
    RettificaGiacenzaReconciliationRequiredError,
    RettificaGiacenzaStockError,
    RettificaGiacenzaVarietaNotFoundError,
)
from .models import RettificaGiacenza, RettificaGiacenzaAuthority, RettificaGiacenzaResult
from .ports import RettificaGiacenzaWriter
from .service import RettificaGiacenzaService

__all__ = [
    "InvalidRettificaGiacenzaCommandError",
    "RettificaGiacenza",
    "RettificaGiacenzaAuthority",
    "RettificaGiacenzaCommitOutcomeUncertainError",
    "RettificaGiacenzaCommitRolledBackError",
    "RettificaGiacenzaConcurrencyError",
    "RettificaGiacenzaError",
    "RettificaGiacenzaIdempotencyConflictError",
    "RettificaGiacenzaIdentityUnavailableError",
    "RettificaGiacenzaOrigineError",
    "RettificaGiacenzaPersistenceInvariantError",
    "RettificaGiacenzaReconciliationRequiredError",
    "RettificaGiacenzaResult",
    "RettificaGiacenzaService",
    "RettificaGiacenzaStockError",
    "RettificaGiacenzaVarietaNotFoundError",
    "RettificaGiacenzaWriter",
]
