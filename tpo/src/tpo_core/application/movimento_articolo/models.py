"""Contratti immutabili del boundary MOVIMENTO_ARTICOLO V1.

Autorità: docs/architecture/ARTICOLO_AUTHORITY_FREEZE.md. Pubblica un
MOVIMENTO_MAGAZZINO su un ARTICOLO (anziché su una VARIETA), incrementando o
decrementando lo STOCK_ARTICOLI corrispondente. Nessuna origine
RACCOLTA/CONSEGNA è ammessa per un movimento ARTICOLO (fisicamente non
applicabile, Sezione 3 del freeze): ``origine_tipo`` è sempre fuori
dall'insieme {RACCOLTA, CONSEGNA}. Il verso (``direzione``) è derivato dal
``tipo`` per CARICO/SCARICO; per RETTIFICA deve essere dichiarato
esplicitamente dal chiamante (coerente con MOVIMENTI_MAGAZZINO.md: "Il verso
della variazione ... è distinto dal tipo di MOVIMENTO").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib

from ...domain.identifiers import ActorId, ArticoloId, MovimentoId
from ...domain.states import MovimentoDirection, MovimentoType
from .errors import InvalidMovimentoArticoloCommandError

UNITA_MISURA_VALIDE = ("SET", "GRAM", "UNIT")


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidMovimentoArticoloCommandError(
            f"{name} deve essere testo normalizzato non vuoto."
        )


def _frame(value: str) -> str:
    return f"{len(value.encode('utf-8'))}:{value}"


def _quantita(value: Decimal) -> Decimal:
    if isinstance(value, (float, bool)):
        raise InvalidMovimentoArticoloCommandError(
            "quantita non accetta valori float o booleani."
        )
    if not isinstance(value, Decimal):
        raise InvalidMovimentoArticoloCommandError("quantita deve essere un Decimal.")
    if not value.is_finite() or value <= 0 or value.as_tuple().exponent < -6:
        raise InvalidMovimentoArticoloCommandError(
            "quantita deve essere positiva, finita e con massimo sei decimali."
        )
    return value


def _tipo(value: object) -> MovimentoType:
    if isinstance(value, MovimentoType):
        return value
    if isinstance(value, str):
        try:
            return MovimentoType(value)
        except ValueError as exc:
            raise InvalidMovimentoArticoloCommandError("tipo non valido.") from exc
    raise InvalidMovimentoArticoloCommandError("tipo non valido.")


def _unita_misura(value: object) -> str:
    if not isinstance(value, str) or value not in UNITA_MISURA_VALIDE:
        raise InvalidMovimentoArticoloCommandError(
            f"unita_misura deve essere una tra {UNITA_MISURA_VALIDE}."
        )
    return value


def _direzione_per(tipo: MovimentoType, direzione: object) -> MovimentoDirection:
    if tipo == MovimentoType.CARICO:
        if direzione is not None:
            raise InvalidMovimentoArticoloCommandError(
                "direzione non va dichiarata per CARICO: è implicita (POSITIVO)."
            )
        return MovimentoDirection.POSITIVO
    if tipo == MovimentoType.SCARICO:
        if direzione is not None:
            raise InvalidMovimentoArticoloCommandError(
                "direzione non va dichiarata per SCARICO: è implicita (NEGATIVO)."
            )
        return MovimentoDirection.NEGATIVO
    # RETTIFICA: il verso non è implicito, va dichiarato dal chiamante.
    if isinstance(direzione, MovimentoDirection):
        return direzione
    if isinstance(direzione, str):
        try:
            return MovimentoDirection(direzione)
        except ValueError as exc:
            raise InvalidMovimentoArticoloCommandError(
                "direzione non valida per RETTIFICA."
            ) from exc
    raise InvalidMovimentoArticoloCommandError(
        "direzione è obbligatoria e va dichiarata esplicitamente per RETTIFICA."
    )


@dataclass(frozen=True)
class MovimentoArticoloAuthority:
    actor: ActorId
    reason: str
    correlation_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidMovimentoArticoloCommandError("actor non valido.")
        for name, value in (("reason", self.reason), ("correlation_id", self.correlation_id),
                            ("idempotency_key", self.idempotency_key)):
            _text(name, value)


@dataclass(frozen=True)
class RegistraMovimentoArticolo:
    articolo_id: ArticoloId
    tipo: MovimentoType
    quantita: Decimal
    unita_misura: str
    effective_at: datetime
    motivo: str
    authority: MovimentoArticoloAuthority
    direzione: MovimentoDirection | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.articolo_id, ArticoloId):
            raise InvalidMovimentoArticoloCommandError("articolo_id non valido.")
        object.__setattr__(self, "tipo", _tipo(self.tipo))
        object.__setattr__(self, "quantita", _quantita(self.quantita))
        object.__setattr__(self, "unita_misura", _unita_misura(self.unita_misura))
        object.__setattr__(self, "direzione", _direzione_per(self.tipo, self.direzione))
        if (not isinstance(self.effective_at, datetime)
                or self.effective_at.tzinfo is None
                or self.effective_at.utcoffset() is None):
            raise InvalidMovimentoArticoloCommandError("effective_at deve essere aware.")
        _text("motivo", self.motivo)
        if not isinstance(self.authority, MovimentoArticoloAuthority):
            raise InvalidMovimentoArticoloCommandError("authority non valida.")
        object.__setattr__(self, "effective_at", self.effective_at.astimezone(timezone.utc))

    @property
    def canonical_payload(self) -> str:
        values = (
            "MOVIMENTO-ARTICOLO-V1", self.articolo_id.value, self.tipo.value,
            self.direzione.value, _decimal(self.quantita), self.unita_misura,
            self.effective_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            self.motivo,
        )
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RegistraMovimentoArticoloResult:
    movimento_id: MovimentoId
    articolo_id: ArticoloId
    quantita: Decimal
    unita_misura: str
    effective_at: datetime
    recorded_at: datetime
    stock_disponibile: Decimal
    outcome: str

    def __post_init__(self) -> None:
        if not isinstance(self.movimento_id, MovimentoId):
            raise InvalidMovimentoArticoloCommandError("movimento_id non valido.")
        if not isinstance(self.articolo_id, ArticoloId):
            raise InvalidMovimentoArticoloCommandError("articolo_id non valido.")


def _decimal(value: Decimal) -> str:
    normalized = format(value, "f").rstrip("0").rstrip(".")
    return normalized or "0"
