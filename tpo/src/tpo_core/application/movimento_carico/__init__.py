"""Boundary applicativo MOVIMENTO_CARICO_RACCOLTA V1 (RegistraCaricoMagazzino)."""

from .errors import (
    InvalidMovimentoCaricoCommandError,
    MovimentoCaricoCommitOutcomeUncertainError,
    MovimentoCaricoCommitRolledBackError,
    MovimentoCaricoConcurrencyError,
    MovimentoCaricoError,
    MovimentoCaricoIdempotencyConflictError,
    MovimentoCaricoIdentityUnavailableError,
    MovimentoCaricoPersistenceInvariantError,
    MovimentoCaricoRaccoltaNotFoundError,
    MovimentoCaricoReconciliationRequiredError,
    MovimentoCaricoStockUnitMismatchError,
)
from .models import (
    MovimentoCaricoAuthority,
    RegistraCaricoMagazzino,
    RegistraCaricoMagazzinoResult,
)
from .ports import MovimentoCaricoWriter
from .service import MovimentoCaricoService

__all__ = [
    "InvalidMovimentoCaricoCommandError",
    "MovimentoCaricoAuthority",
    "MovimentoCaricoCommitOutcomeUncertainError",
    "MovimentoCaricoCommitRolledBackError",
    "MovimentoCaricoConcurrencyError",
    "MovimentoCaricoError",
    "MovimentoCaricoIdempotencyConflictError",
    "MovimentoCaricoIdentityUnavailableError",
    "MovimentoCaricoPersistenceInvariantError",
    "MovimentoCaricoRaccoltaNotFoundError",
    "MovimentoCaricoReconciliationRequiredError",
    "MovimentoCaricoService",
    "MovimentoCaricoStockUnitMismatchError",
    "MovimentoCaricoWriter",
    "RegistraCaricoMagazzino",
    "RegistraCaricoMagazzinoResult",
]
