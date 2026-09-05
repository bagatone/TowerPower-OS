"""Contratti immutabili del boundary ARTICOLO_COMMISSIONING V1.

Autorità: docs/architecture/ARTICOLO_AUTHORITY_FREEZE.md. ARTICOLO identifica
i materiali che servono alla catena produttiva perché funzioni (substrati,
fertilizzante, packaging, ecc.), distinta da VARIETA (i semi). ``unita_misura``
è l'unità di riferimento per lo STOCK_ARTICOLI di quell'ARTICOLO; non è
imposta alcuna unicità di business-key su ``denominazione`` (nessuna richiesta
da alcuna authority congelata).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib

from ...domain.identifiers import ActorId, ArticoloId
from .errors import InvalidArticoloCommandError

UNITA_MISURA_VALIDE = ("SET", "GRAM", "UNIT")


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidArticoloCommandError(
            f"{name} deve essere testo normalizzato non vuoto."
        )


def _frame(value: str) -> str:
    return f"{len(value.encode('utf-8'))}:{value}"


def _unita_misura(value: object) -> str:
    if not isinstance(value, str) or value not in UNITA_MISURA_VALIDE:
        raise InvalidArticoloCommandError(
            f"unita_misura deve essere una tra {UNITA_MISURA_VALIDE}."
        )
    return value


@dataclass(frozen=True)
class ArticoloCommissioningAuthority:
    actor: ActorId
    reason: str
    correlation_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidArticoloCommandError("actor non valido.")
        for name, value in (("reason", self.reason), ("correlation_id", self.correlation_id),
                            ("idempotency_key", self.idempotency_key)):
            _text(name, value)


@dataclass(frozen=True)
class CommissionArticolo:
    """Comando di commissioning di un nuovo ARTICOLO.

    ``unita_misura`` fissa l'unità di riferimento dello STOCK_ARTICOLI per
    questo ARTICOLO (non convertibile successivamente: ogni MOVIMENTO_ARTICOLO
    deve dichiarare la stessa unità, ARTICOLO_AUTHORITY_FREEZE.md Sezione 4).
    """

    denominazione: str
    unita_misura: str
    authority: ArticoloCommissioningAuthority

    def __post_init__(self) -> None:
        _text("denominazione", self.denominazione)
        object.__setattr__(self, "unita_misura", _unita_misura(self.unita_misura))
        if not isinstance(self.authority, ArticoloCommissioningAuthority):
            raise InvalidArticoloCommandError("authority non valida.")

    @property
    def canonical_payload(self) -> str:
        values = ("ARTICOLO-COMMISSIONING-V1", self.denominazione, self.unita_misura)
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CommissionArticoloResult:
    articolo_id: ArticoloId
    denominazione: str
    unita_misura: str
    recorded_at: datetime
    outcome: str

    def __post_init__(self) -> None:
        if not isinstance(self.articolo_id, ArticoloId):
            raise InvalidArticoloCommandError("articolo_id non valido.")
