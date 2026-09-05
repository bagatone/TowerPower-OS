"""Contratti immutabili del boundary ASSEGNAZIONE_FISICA V1.

Autorità: docs/architecture/ASSEGNAZIONE_FISICA_AUTHORITY_FREEZE.md. Register
Fact-only (append-only): lega una RACCOLTA a una RIGA_ORDINE, con un
riferimento opzionale a una CONSEGNA (`ASSEGNAZIONI.md`). Nessun vincolo di
capienza/quantità imposto dal sistema (Owner Decision
D-ASSEGNAZIONE_FISICA-capacity): `quantita_assegnata` è dichiarativa, non
verificata contro la quantità della RACCOLTA né contro quella della
RIGA_ORDINE. V1 copre solo la Fact di creazione: variazione, rettifica,
riallocazione e annullamento sono deferred a un boundary successivo.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib

from ...domain.identifiers import (
    ActorId, AssegnazioneFisicaId, ConsegnaId, RaccoltaId, RigaOrdineId,
)
from .errors import InvalidAssegnazioneFisicaCommandError

UNITA_MISURA_VALIDE = ("SET", "GRAM", "UNIT")


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidAssegnazioneFisicaCommandError(
            f"{name} deve essere testo normalizzato non vuoto."
        )


def _frame(value: str | None) -> str:
    if value is None:
        return "-1:"
    return f"{len(value.encode('utf-8'))}:{value}"


def _quantita_assegnata(value: Decimal) -> Decimal:
    if isinstance(value, (float, bool)):
        raise InvalidAssegnazioneFisicaCommandError(
            "quantita_assegnata non accetta valori float o booleani."
        )
    if not isinstance(value, Decimal):
        raise InvalidAssegnazioneFisicaCommandError("quantita_assegnata deve essere un Decimal.")
    if not value.is_finite() or value <= 0 or value.as_tuple().exponent < -6:
        raise InvalidAssegnazioneFisicaCommandError(
            "quantita_assegnata deve essere positiva, finita e con massimo sei decimali."
        )
    return value


def _unita_misura(value: object) -> str:
    if not isinstance(value, str) or value not in UNITA_MISURA_VALIDE:
        raise InvalidAssegnazioneFisicaCommandError(
            f"unita_misura deve essere una tra {UNITA_MISURA_VALIDE}."
        )
    return value


@dataclass(frozen=True)
class AssegnazioneFisicaAuthority:
    actor: ActorId
    reason: str
    correlation_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidAssegnazioneFisicaCommandError("actor non valido.")
        for name, value in (("reason", self.reason), ("correlation_id", self.correlation_id),
                            ("idempotency_key", self.idempotency_key)):
            _text(name, value)


@dataclass(frozen=True)
class RegistraAssegnazioneFisica:
    raccolta_id: RaccoltaId
    riga_ordine_id: RigaOrdineId
    quantita_assegnata: Decimal
    unita_misura: str
    effective_at: datetime
    motivo: str
    authority: AssegnazioneFisicaAuthority
    consegna_id: ConsegnaId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.raccolta_id, RaccoltaId):
            raise InvalidAssegnazioneFisicaCommandError("raccolta_id non valido.")
        if not isinstance(self.riga_ordine_id, RigaOrdineId):
            raise InvalidAssegnazioneFisicaCommandError("riga_ordine_id non valido.")
        if self.consegna_id is not None and not isinstance(self.consegna_id, ConsegnaId):
            raise InvalidAssegnazioneFisicaCommandError("consegna_id non valido.")
        object.__setattr__(
            self, "quantita_assegnata", _quantita_assegnata(self.quantita_assegnata)
        )
        object.__setattr__(self, "unita_misura", _unita_misura(self.unita_misura))
        if (not isinstance(self.effective_at, datetime)
                or self.effective_at.tzinfo is None
                or self.effective_at.utcoffset() is None):
            raise InvalidAssegnazioneFisicaCommandError("effective_at deve essere aware.")
        _text("motivo", self.motivo)
        if not isinstance(self.authority, AssegnazioneFisicaAuthority):
            raise InvalidAssegnazioneFisicaCommandError("authority non valida.")
        object.__setattr__(self, "effective_at", self.effective_at.astimezone(timezone.utc))

    @property
    def canonical_payload(self) -> str:
        values = (
            "ASSEGNAZIONE-FISICA-V1", self.raccolta_id.value, self.riga_ordine_id.value,
            self.consegna_id.value if self.consegna_id is not None else None,
            _decimal(self.quantita_assegnata), self.unita_misura,
            self.effective_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            self.motivo,
        )
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RegistraAssegnazioneFisicaResult:
    assegnazione_fisica_id: AssegnazioneFisicaId
    raccolta_id: RaccoltaId
    riga_ordine_id: RigaOrdineId
    quantita_assegnata: Decimal
    unita_misura: str
    effective_at: datetime
    recorded_at: datetime
    outcome: str
    consegna_id: ConsegnaId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.assegnazione_fisica_id, AssegnazioneFisicaId):
            raise InvalidAssegnazioneFisicaCommandError("assegnazione_fisica_id non valido.")
        if not isinstance(self.raccolta_id, RaccoltaId):
            raise InvalidAssegnazioneFisicaCommandError("raccolta_id non valido.")
        if not isinstance(self.riga_ordine_id, RigaOrdineId):
            raise InvalidAssegnazioneFisicaCommandError("riga_ordine_id non valido.")


def _decimal(value: Decimal) -> str:
    normalized = format(value, "f").rstrip("0").rstrip(".")
    return normalized or "0"
