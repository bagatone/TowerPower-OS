"""Contratti immutabili del Uscita Recording Boundary V1 e del Uscita Correzione V1."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib

from ...domain.identifiers import ActorId, UscitaId
from ...domain.states import CategoriaUscita, MetodoPagamento
from .errors import (
    InvalidUscitaAmountError, InvalidUscitaCommandError, InvalidUscitaEffectiveAtError,
)


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidUscitaCommandError(f"{name} deve essere testo normalizzato non vuoto.")


@dataclass(frozen=True)
class UscitaAuthority:
    actor: ActorId
    reason: str
    correlation_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidUscitaCommandError("actor non valido.")
        for name, value in (("reason", self.reason), ("correlation_id", self.correlation_id),
                            ("idempotency_key", self.idempotency_key)):
            _text(name, value)


def _positive_amount(value: object) -> Decimal:
    """Importo ordinario: positivo, finito, massimo due decimali (valuta)."""
    if isinstance(value, (float, bool)):
        raise InvalidUscitaAmountError("importo non accetta float o booleani.")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidUscitaAmountError("importo deve essere decimale.") from exc
    if not result.is_finite() or result <= 0 or result.as_tuple().exponent < -2:
        raise InvalidUscitaAmountError(
            "importo deve essere positivo, finito e con massimo due decimali."
        )
    return result


def _signed_amount(value: object) -> Decimal:
    """Importo di rettifica: non zero, finito, massimo due decimali, segno libero."""
    if isinstance(value, (float, bool)):
        raise InvalidUscitaAmountError("importo non accetta float o booleani.")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidUscitaAmountError("importo deve essere decimale.") from exc
    if not result.is_finite() or result == 0 or result.as_tuple().exponent < -2:
        raise InvalidUscitaAmountError(
            "L'importo della rettifica deve essere non zero, finito e con "
            "massimo due decimali."
        )
    return result


def _metodo(value: object) -> MetodoPagamento:
    if isinstance(value, MetodoPagamento):
        return value
    try:
        return MetodoPagamento(value)
    except (ValueError, TypeError) as exc:
        raise InvalidUscitaCommandError("metodo di pagamento non valido.") from exc


def _categoria(value: object) -> CategoriaUscita:
    if isinstance(value, CategoriaUscita):
        return value
    try:
        return CategoriaUscita(value)
    except (ValueError, TypeError) as exc:
        raise InvalidUscitaCommandError("categoria non valida.") from exc


def _data(value: object, name: str) -> date:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise InvalidUscitaEffectiveAtError(f"{name} deve essere una data (non un datetime).")
    return value


@dataclass(frozen=True)
class RegistraUscita:
    importo: Decimal
    data_uscita: date
    categoria: CategoriaUscita
    beneficiario: str
    metodo: MetodoPagamento
    authority: UscitaAuthority
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "importo", _positive_amount(self.importo))
        object.__setattr__(self, "data_uscita", _data(self.data_uscita, "data_uscita"))
        object.__setattr__(self, "categoria", _categoria(self.categoria))
        _text("beneficiario", self.beneficiario)
        object.__setattr__(self, "metodo", _metodo(self.metodo))
        if not isinstance(self.authority, UscitaAuthority):
            raise InvalidUscitaCommandError("authority non valida.")
        if self.note is not None:
            _text("note", self.note)

    @property
    def canonical_payload(self) -> str:
        values = (
            "USCITA-RECORDING-V1", _decimal(self.importo), self.data_uscita.isoformat(),
            self.categoria.value, self.beneficiario, self.metodo.value, self.note,
        )
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RegistraUscitaResult:
    uscita_id: UscitaId
    importo: Decimal
    data_uscita: date
    categoria: CategoriaUscita
    beneficiario: str
    metodo: MetodoPagamento
    recorded_at: datetime
    outcome: str


def _frame(value: str | None) -> str:
    return "-1:" if value is None else f"{len(value.encode('utf-8'))}:{value}"


def _decimal(value: Decimal) -> str:
    normalized = format(value, "f").rstrip("0").rstrip(".")
    return normalized or "0"


@dataclass(frozen=True)
class CorreggiUscita:
    original_uscita_id: UscitaId
    importo: Decimal
    data_uscita: date
    categoria: CategoriaUscita
    beneficiario: str
    metodo: MetodoPagamento
    authority: UscitaAuthority
    note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.original_uscita_id, UscitaId):
            raise InvalidUscitaCommandError("original_uscita_id non valido.")
        object.__setattr__(self, "importo", _signed_amount(self.importo))
        object.__setattr__(self, "data_uscita", _data(self.data_uscita, "data_uscita"))
        object.__setattr__(self, "categoria", _categoria(self.categoria))
        _text("beneficiario", self.beneficiario)
        object.__setattr__(self, "metodo", _metodo(self.metodo))
        if not isinstance(self.authority, UscitaAuthority):
            raise InvalidUscitaCommandError("authority non valida.")
        if self.note is not None:
            _text("note", self.note)

    @property
    def canonical_payload(self) -> str:
        values = (
            "USCITA-CORREZIONE-V1", self.original_uscita_id.value, _decimal(self.importo),
            self.data_uscita.isoformat(), self.categoria.value, self.beneficiario,
            self.metodo.value, self.note,
        )
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CorreggiUscitaResult:
    uscita_id: UscitaId
    original_uscita_id: UscitaId
    importo: Decimal
    data_uscita: date
    categoria: CategoriaUscita
    beneficiario: str
    metodo: MetodoPagamento
    recorded_at: datetime
    outcome: str
