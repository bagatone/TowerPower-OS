"""Comandi e risultati immutabili dell'emissione FATTURA V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib

from ...domain.identifiers import ActorId, ClienteId, ConsegnaId, NumeroFattura
from .errors import InvalidEmitFatturaCommandError


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidEmitFatturaCommandError(f"{name} deve essere testo normalizzato non vuoto.")


def _frame(value: str | None) -> str:
    if value is None:
        return "-1:"
    return f"{len(value.encode('utf-8'))}:{value}"


@dataclass(frozen=True)
class EmitFatturaAuthority:
    actor: ActorId
    reason: str
    correlation_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidEmitFatturaCommandError("actor non valido.")
        for name, value in (("reason", self.reason), ("correlation_id", self.correlation_id),
                            ("idempotency_key", self.idempotency_key)):
            _text(name, value)


@dataclass(frozen=True)
class EmitFattura:
    """Emissione atomica di una FATTURA a partire da una o più CONSEGNE evase.

    Scope V1 (FATTURA_AUTHORITY_FREEZE.md, sezione 11): nessuna rettifica.
    RectifyFattura resta esplicitamente fuori scope in questo round.
    """

    cliente_id: ClienteId
    consegna_ids: tuple[ConsegnaId, ...]
    data_emissione: date
    authority: EmitFatturaAuthority

    def __post_init__(self) -> None:
        if not isinstance(self.cliente_id, ClienteId):
            raise InvalidEmitFatturaCommandError("cliente_id non valido.")
        if not isinstance(self.consegna_ids, tuple) or not self.consegna_ids:
            raise InvalidEmitFatturaCommandError("consegna_ids deve essere una tuple non vuota.")
        if any(not isinstance(item, ConsegnaId) for item in self.consegna_ids):
            raise InvalidEmitFatturaCommandError("consegna_ids contiene elementi non validi.")
        if len({item.value for item in self.consegna_ids}) != len(self.consegna_ids):
            raise InvalidEmitFatturaCommandError("Ogni CONSEGNA può comparire una sola volta per FATTURA.")
        if not isinstance(self.data_emissione, date) or isinstance(self.data_emissione, datetime):
            raise InvalidEmitFatturaCommandError("data_emissione non valida.")
        if not isinstance(self.authority, EmitFatturaAuthority):
            raise InvalidEmitFatturaCommandError("authority non valida.")

    @property
    def canonical_payload(self) -> str:
        values = (
            "FATTURA-EMISSIONE-V1", self.cliente_id.value, self.data_emissione.isoformat(),
            *[item.value for item in self.consegna_ids],
        )
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EmitFatturaResult:
    fattura_id: int
    outcome: str
    numero_fattura: NumeroFattura
    cliente_id: ClienteId
    data_emissione: date
    scadenza: date
    totale_netto: Decimal
    totale_igic: Decimal
    totale: Decimal
    consegna_count: int
    riga_count: int
    recorded_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.fattura_id, int) or isinstance(self.fattura_id, bool) or self.fattura_id <= 0:
            raise InvalidEmitFatturaCommandError("fattura_id interno non valido.")
        if not isinstance(self.numero_fattura, NumeroFattura):
            raise InvalidEmitFatturaCommandError("numero_fattura non valido.")
