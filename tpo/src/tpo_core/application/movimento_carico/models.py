"""Contratti immutabili del Movimento Carico Raccolta Boundary V1.

Autorità: docs/architecture/MOVIMENTO_CARICO_AUTHORITY_FREEZE.md (V1,
percorso GRAM, Owner Decision D11/D12) e il suo addendum V2 (percorso SET
per prodotto venduto a unità intera, mai tagliato/pesato -- Owner Decision
D13/D14, 19/9/2026). Pubblica un carico di magazzino (MOVIMENTO tipo
CARICO) originato da una RACCOLTA reale, incrementando lo STOCK della
VARIETA corrispondente.

Due percorsi, selezionati da ``unita_misura``, mai misti sulla stessa
VARIETA (``tpo.stock.varieta_id`` resta PRIMARY KEY: una sola unità di
misura di stock per VARIETA, per sempre):

- GRAM (V1, invariato): la quantità è dichiarata dall'operatore (peso
  fisicamente accertato al momento della pubblicazione, Owner Decision
  D11) -- non è calcolata dalla quantità in SET della RACCOLTA tramite
  alcun fattore di resa, che non esiste in alcuna authority congelata.
  Per prodotto tagliato/pesato (es. futura verdura da torre verticale).
- SET (V2, nuovo): nessun peso da dichiarare. La quantità caricata è
  esattamente la quantità SET già dichiarata sulla RACCOLTA collegata
  (Owner Decision D14): per prodotto mai tagliato, venduto come unità
  intera così com'è (i microgreens di oggi), "N SET raccolti" e "N SET a
  magazzino" sono la stessa unità fisica, senza passaggi intermedi che
  introducano incertezza o richiedano una nuova dichiarazione.

Una stessa RACCOLTA può originare più CARICHI parziali nel tempo (Owner
Decision D12): raccolta_id è un riferimento di tracciabilità/audit, non un
vincolo di quantità massima cumulabile.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib

from ...domain.identifiers import ActorId, MovimentoId, RaccoltaId, VarietaId
from ...domain.quantities import UnitOfMeasure
from .errors import InvalidMovimentoCaricoCommandError

CARICO_UNITS = frozenset({UnitOfMeasure.GRAM, UnitOfMeasure.SET})


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidMovimentoCaricoCommandError(
            f"{name} deve essere testo normalizzato non vuoto."
        )


def _frame(value: str) -> str:
    return f"{len(value.encode('utf-8'))}:{value}"


def _quantita_pesata(value: Decimal) -> Decimal:
    if isinstance(value, (float, bool)):
        raise InvalidMovimentoCaricoCommandError(
            "quantita_pesata non accetta valori float o booleani."
        )
    if not isinstance(value, Decimal):
        raise InvalidMovimentoCaricoCommandError("quantita_pesata deve essere un Decimal.")
    if not value.is_finite() or value <= 0 or value.as_tuple().exponent < -6:
        raise InvalidMovimentoCaricoCommandError(
            "quantita_pesata deve essere positiva, finita e con massimo sei decimali."
        )
    return value


@dataclass(frozen=True)
class MovimentoCaricoAuthority:
    actor: ActorId
    reason: str
    correlation_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidMovimentoCaricoCommandError("actor non valido.")
        for name, value in (("reason", self.reason), ("correlation_id", self.correlation_id),
                            ("idempotency_key", self.idempotency_key)):
            _text(name, value)


@dataclass(frozen=True)
class RegistraCaricoMagazzino:
    """Comando di pubblicazione di un CARICO originato da una RACCOLTA.

    ``raccolta_id`` è un riferimento di tracciabilità (quale evento di
    raccolta ha fisicamente originato il carico), non una fonte di calcolo
    della quantità in GRAM (Owner Decision D11/D12). Per il percorso SET
    (Owner Decision D14) è invece esattamente la fonte della quantità:
    ``quantita_pesata`` deve restare ``None`` e la quantità viene risolta
    dal writer dalla RACCOLTA stessa (già in SET, mai un nuovo numero).
    """

    raccolta_id: RaccoltaId
    unita_misura: UnitOfMeasure
    quantita_pesata: Decimal | None
    effective_at: datetime
    motivo: str
    authority: MovimentoCaricoAuthority

    def __post_init__(self) -> None:
        if not isinstance(self.raccolta_id, RaccoltaId):
            raise InvalidMovimentoCaricoCommandError("raccolta_id non valido.")
        if self.unita_misura not in CARICO_UNITS:
            raise InvalidMovimentoCaricoCommandError(
                "unita_misura deve essere GRAM o SET per un CARICO."
            )
        if self.unita_misura is UnitOfMeasure.GRAM:
            if self.quantita_pesata is None:
                raise InvalidMovimentoCaricoCommandError(
                    "quantita_pesata e' obbligatoria per un CARICO in GRAM."
                )
            object.__setattr__(self, "quantita_pesata", _quantita_pesata(self.quantita_pesata))
        else:
            if self.quantita_pesata is not None:
                raise InvalidMovimentoCaricoCommandError(
                    "quantita_pesata non e' ammessa per un CARICO in SET: la quantita' e' "
                    "sempre presa dalla RACCOLTA collegata, mai dichiarata di nuovo (D14)."
                )
        if (not isinstance(self.effective_at, datetime)
                or self.effective_at.tzinfo is None
                or self.effective_at.utcoffset() is None):
            raise InvalidMovimentoCaricoCommandError("effective_at deve essere aware.")
        _text("motivo", self.motivo)
        if not isinstance(self.authority, MovimentoCaricoAuthority):
            raise InvalidMovimentoCaricoCommandError("authority non valida.")
        object.__setattr__(self, "effective_at", self.effective_at.astimezone(timezone.utc))

    @property
    def canonical_payload(self) -> str:
        quantity_component = (
            _decimal(self.quantita_pesata) if self.unita_misura is UnitOfMeasure.GRAM
            else "FROM_RACCOLTA"
        )
        values = (
            "MOVIMENTO-CARICO-RACCOLTA-V1", self.raccolta_id.value, self.unita_misura.value,
            quantity_component,
            self.effective_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            self.motivo,
        )
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RegistraCaricoMagazzinoResult:
    movimento_id: MovimentoId
    raccolta_id: RaccoltaId
    varieta_id: VarietaId
    unita_misura: UnitOfMeasure
    quantita: Decimal
    effective_at: datetime
    recorded_at: datetime
    stock_disponibile: Decimal
    outcome: str

    def __post_init__(self) -> None:
        if not isinstance(self.movimento_id, MovimentoId):
            raise InvalidMovimentoCaricoCommandError("movimento_id non valido.")
        if not isinstance(self.raccolta_id, RaccoltaId):
            raise InvalidMovimentoCaricoCommandError("raccolta_id non valido.")
        if not isinstance(self.varieta_id, VarietaId):
            raise InvalidMovimentoCaricoCommandError("varieta_id non valido.")
        if self.unita_misura not in CARICO_UNITS:
            raise InvalidMovimentoCaricoCommandError("unita_misura del risultato non valida.")


def _decimal(value: Decimal) -> str:
    normalized = format(value, "f").rstrip("0").rstrip(".")
    return normalized or "0"
