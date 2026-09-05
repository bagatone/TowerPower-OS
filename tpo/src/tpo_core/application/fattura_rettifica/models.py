"""Comandi e risultati immutabili della rettifica FATTURA V1 (RectifyFattura).

Autorità: docs/architecture/RECTIFY_FATTURA_AUTHORITY_FREEZE.md. Implementa la
riserva già approvata in FATTURA_AUTHORITY_FREEZE.md §16 (Owner Decision D7):
una rettifica è una nuova FATTURA, con proprio numero_fattura dalla stessa
serie annuale, che corregge una o più righe specifiche della fattura
originale (Owner Decision D8) — non l'intera fattura in blocco.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib

from ...domain.identifiers import ActorId, ClienteId, NumeroFattura
from .errors import InvalidRectifyFatturaCommandError


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidRectifyFatturaCommandError(
            f"{name} deve essere testo normalizzato non vuoto."
        )


def _frame(value: str) -> str:
    return f"{len(value.encode('utf-8'))}:{value}"


@dataclass(frozen=True)
class RectifyFatturaAuthority:
    actor: ActorId
    reason: str
    correlation_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidRectifyFatturaCommandError("actor non valido.")
        for name, value in (("reason", self.reason), ("correlation_id", self.correlation_id),
                            ("idempotency_key", self.idempotency_key)):
            _text(name, value)


@dataclass(frozen=True)
class RettificaRigaFattura:
    """Una singola correzione: quale riga della fattura originale (per
    posizione) e di quanto (con segno, mai zero — Owner Decision D9)."""

    posizione_originale: int
    quantita: Decimal

    def __post_init__(self) -> None:
        if (not isinstance(self.posizione_originale, int)
                or isinstance(self.posizione_originale, bool)
                or self.posizione_originale <= 0):
            raise InvalidRectifyFatturaCommandError("posizione_originale deve essere un intero positivo.")
        if not isinstance(self.quantita, Decimal) or not self.quantita.is_finite():
            raise InvalidRectifyFatturaCommandError("quantita deve essere un Decimal finito.")
        if self.quantita == 0:
            raise InvalidRectifyFatturaCommandError("quantita di rettifica non può essere zero.")


@dataclass(frozen=True)
class RectifyFattura:
    rettifica_di: NumeroFattura
    righe: tuple[RettificaRigaFattura, ...]
    data_emissione: date
    authority: RectifyFatturaAuthority

    def __post_init__(self) -> None:
        if not isinstance(self.rettifica_di, NumeroFattura):
            raise InvalidRectifyFatturaCommandError("rettifica_di non valido.")
        if not isinstance(self.righe, tuple) or not self.righe:
            raise InvalidRectifyFatturaCommandError("righe deve essere una tuple non vuota.")
        if any(not isinstance(item, RettificaRigaFattura) for item in self.righe):
            raise InvalidRectifyFatturaCommandError("righe contiene elementi non validi.")
        posizioni = [item.posizione_originale for item in self.righe]
        if len(set(posizioni)) != len(posizioni):
            raise InvalidRectifyFatturaCommandError(
                "Ogni posizione originale può essere corretta una sola volta per comando."
            )
        if not isinstance(self.data_emissione, date) or isinstance(self.data_emissione, datetime):
            raise InvalidRectifyFatturaCommandError("data_emissione non valida.")
        if not isinstance(self.authority, RectifyFatturaAuthority):
            raise InvalidRectifyFatturaCommandError("authority non valida.")

    @property
    def canonical_payload(self) -> str:
        righe_ordinate = sorted(self.righe, key=lambda item: item.posizione_originale)
        values = [
            "FATTURA-RETTIFICA-V1", self.rettifica_di.value, self.data_emissione.isoformat(),
        ]
        for riga in righe_ordinate:
            values.append(str(riga.posizione_originale))
            values.append(str(riga.quantita))
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RectifyFatturaResult:
    fattura_id: int
    outcome: str
    numero_fattura: NumeroFattura
    rettifica_di: NumeroFattura
    cliente_id: ClienteId
    data_emissione: date
    scadenza: date
    totale_netto: Decimal
    totale_igic: Decimal
    totale: Decimal
    riga_count: int
    recorded_at: datetime

    def __post_init__(self) -> None:
        if (not isinstance(self.fattura_id, int) or isinstance(self.fattura_id, bool)
                or self.fattura_id <= 0):
            raise InvalidRectifyFatturaCommandError("fattura_id interno non valido.")
        if not isinstance(self.numero_fattura, NumeroFattura):
            raise InvalidRectifyFatturaCommandError("numero_fattura non valido.")
        if not isinstance(self.rettifica_di, NumeroFattura):
            raise InvalidRectifyFatturaCommandError("rettifica_di non valido.")
