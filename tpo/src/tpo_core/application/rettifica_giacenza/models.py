"""Contratti immutabili del boundary RETTIFICA_GIACENZA V1.

Uno STOCK puo' contenere merce che fisicamente non esiste piu' (venduta o
uscita senza che l'uscita sia mai stata registrata nel sistema). Questo
boundary NON altera nessun fatto gia' committato (raccolte, carichi, consegne):
scrive un nuovo MOVIMENTO SCARICO con origine_tipo 'RETTIFICA_GIACENZA',
motivo obbligatorio, e spiega da quali lotti (SEMINE/codici di tracciabilita')
la quantita' e' uscita, cosi' che quei lotti non risultino piu' disponibili
per le bolle future. Solo diminuzioni: nessuna rettifica in aumento esiste in
questo boundary (un aumento reale nasce da RACCOLTA + CARICO).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib

from ...domain.identifiers import ActorId, MovimentoId, SeminaId, VarietaId
from ...domain.quantities import UnitOfMeasure
from .errors import InvalidRettificaGiacenzaCommandError

RETTIFICA_UNITS = frozenset({UnitOfMeasure.GRAM, UnitOfMeasure.SET})


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidRettificaGiacenzaCommandError(
            f"{name} deve essere testo normalizzato non vuoto."
        )


def _frame(value: str) -> str:
    return f"{len(value.encode('utf-8'))}:{value}"


def _decimal(value: Decimal) -> str:
    normalized = format(value, "f").rstrip("0").rstrip(".")
    return normalized or "0"


def _quantita(value: Decimal) -> Decimal:
    if isinstance(value, (float, bool)) or not isinstance(value, Decimal):
        raise InvalidRettificaGiacenzaCommandError("quantita deve essere un Decimal.")
    if not value.is_finite() or value <= 0 or value.as_tuple().exponent < -6:
        raise InvalidRettificaGiacenzaCommandError(
            "quantita deve essere positiva, finita e con massimo sei decimali."
        )
    return value


@dataclass(frozen=True)
class RettificaGiacenzaAuthority:
    actor: ActorId
    reason: str
    correlation_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidRettificaGiacenzaCommandError("actor non valido.")
        for name, value in (("reason", self.reason), ("correlation_id", self.correlation_id),
                            ("idempotency_key", self.idempotency_key)):
            _text(name, value)


@dataclass(frozen=True)
class RettificaGiacenza:
    """Riduce la giacenza di una VARIETA di ``quantita`` nell'unita' indicata.

    ``origin_semina`` (opzionale) dichiara da quale SEMINA proviene la merce
    che non esiste piu': se presente si consumano esattamente i lotti di quella
    semina (o il comando e' rifiutato); altrimenti FIFO come per le consegne.
    """

    varieta_id: VarietaId
    unita_misura: UnitOfMeasure
    quantita: Decimal
    effective_at: datetime
    motivo: str
    authority: RettificaGiacenzaAuthority
    origin_semina: SeminaId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.varieta_id, VarietaId):
            raise InvalidRettificaGiacenzaCommandError("varieta_id non valido.")
        if self.unita_misura not in RETTIFICA_UNITS:
            raise InvalidRettificaGiacenzaCommandError("unita_misura deve essere GRAM o SET.")
        object.__setattr__(self, "quantita", _quantita(self.quantita))
        if (not isinstance(self.effective_at, datetime)
                or self.effective_at.tzinfo is None
                or self.effective_at.utcoffset() is None):
            raise InvalidRettificaGiacenzaCommandError("effective_at deve essere aware.")
        _text("motivo", self.motivo)
        if not isinstance(self.authority, RettificaGiacenzaAuthority):
            raise InvalidRettificaGiacenzaCommandError("authority non valida.")
        if self.origin_semina is not None and not isinstance(self.origin_semina, SeminaId):
            raise InvalidRettificaGiacenzaCommandError("origin_semina non valida.")
        object.__setattr__(self, "effective_at", self.effective_at.astimezone(timezone.utc))

    @property
    def canonical_payload(self) -> str:
        values = (
            "MOVIMENTO-RETTIFICA-GIACENZA-V1", self.varieta_id.value,
            self.unita_misura.value, _decimal(self.quantita),
            self.effective_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            self.motivo,
            "" if self.origin_semina is None else self.origin_semina.value,
        )
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RettificaGiacenzaResult:
    movimento_id: MovimentoId
    varieta_id: VarietaId
    unita_misura: UnitOfMeasure
    quantita: Decimal
    effective_at: datetime
    recorded_at: datetime
    stock_disponibile: Decimal
    outcome: str
