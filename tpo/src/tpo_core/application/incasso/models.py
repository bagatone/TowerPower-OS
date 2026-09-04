"""Contratti immutabili del Incasso Recording Boundary V1 e del Incasso Correzione V1."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib

from ...domain.identifiers import ActorId, IncassoId, NumeroFattura
from ...domain.states import MetodoPagamento
from .errors import (
    InvalidIncassoAmountError, InvalidIncassoCommandError, InvalidIncassoEffectiveAtError,
)


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidIncassoCommandError(f"{name} deve essere testo normalizzato non vuoto.")


@dataclass(frozen=True)
class IncassoAuthority:
    actor: ActorId
    reason: str
    correlation_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidIncassoCommandError("actor non valido.")
        for name, value in (("reason", self.reason), ("correlation_id", self.correlation_id),
                            ("idempotency_key", self.idempotency_key)):
            _text(name, value)


def _positive_amount(value: object) -> Decimal:
    """Importo ordinario: positivo, finito, massimo due decimali (valuta)."""
    if isinstance(value, (float, bool)):
        raise InvalidIncassoAmountError("importo non accetta float o booleani.")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidIncassoAmountError("importo deve essere decimale.") from exc
    if not result.is_finite() or result <= 0 or result.as_tuple().exponent < -2:
        raise InvalidIncassoAmountError(
            "importo deve essere positivo, finito e con massimo due decimali."
        )
    return result


def _signed_amount(value: object) -> Decimal:
    """Importo di rettifica: non zero, finito, massimo due decimali, segno libero."""
    if isinstance(value, (float, bool)):
        raise InvalidIncassoAmountError("importo non accetta float o booleani.")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidIncassoAmountError("importo deve essere decimale.") from exc
    if not result.is_finite() or result == 0 or result.as_tuple().exponent < -2:
        raise InvalidIncassoAmountError(
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
        raise InvalidIncassoCommandError("metodo di pagamento non valido.") from exc


def _data(value: object, name: str) -> date:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise InvalidIncassoEffectiveAtError(f"{name} deve essere una data (non un datetime).")
    return value


@dataclass(frozen=True)
class RegistraIncasso:
    fattura_numero: NumeroFattura
    importo: Decimal
    data_incasso: date
    metodo: MetodoPagamento
    authority: IncassoAuthority
    note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.fattura_numero, NumeroFattura):
            raise InvalidIncassoCommandError("fattura_numero non valido.")
        object.__setattr__(self, "importo", _positive_amount(self.importo))
        object.__setattr__(self, "data_incasso", _data(self.data_incasso, "data_incasso"))
        object.__setattr__(self, "metodo", _metodo(self.metodo))
        if not isinstance(self.authority, IncassoAuthority):
            raise InvalidIncassoCommandError("authority non valida.")
        if self.note is not None:
            _text("note", self.note)

    @property
    def canonical_payload(self) -> str:
        values = (
            "INCASSO-RECORDING-V1", self.fattura_numero.value, _decimal(self.importo),
            self.data_incasso.isoformat(), self.metodo.value, self.note,
        )
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RegistraIncassoResult:
    incasso_id: IncassoId
    fattura_numero: NumeroFattura
    importo: Decimal
    data_incasso: date
    metodo: MetodoPagamento
    recorded_at: datetime
    outcome: str


def _frame(value: str | None) -> str:
    return "-1:" if value is None else f"{len(value.encode('utf-8'))}:{value}"


def _decimal(value: Decimal) -> str:
    normalized = format(value, "f").rstrip("0").rstrip(".")
    return normalized or "0"


@dataclass(frozen=True)
class CorreggiIncasso:
    original_incasso_id: IncassoId
    fattura_numero: NumeroFattura
    importo: Decimal
    data_incasso: date
    metodo: MetodoPagamento
    authority: IncassoAuthority
    note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.original_incasso_id, IncassoId):
            raise InvalidIncassoCommandError("original_incasso_id non valido.")
        if not isinstance(self.fattura_numero, NumeroFattura):
            raise InvalidIncassoCommandError("fattura_numero non valido.")
        object.__setattr__(self, "importo", _signed_amount(self.importo))
        object.__setattr__(self, "data_incasso", _data(self.data_incasso, "data_incasso"))
        object.__setattr__(self, "metodo", _metodo(self.metodo))
        if not isinstance(self.authority, IncassoAuthority):
            raise InvalidIncassoCommandError("authority non valida.")
        if self.note is not None:
            _text("note", self.note)

    @property
    def canonical_payload(self) -> str:
        values = (
            "INCASSO-CORREZIONE-V1", self.original_incasso_id.value, self.fattura_numero.value,
            _decimal(self.importo), self.data_incasso.isoformat(), self.metodo.value, self.note,
        )
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CorreggiIncassoResult:
    incasso_id: IncassoId
    original_incasso_id: IncassoId
    fattura_numero: NumeroFattura
    importo: Decimal
    data_incasso: date
    metodo: MetodoPagamento
    recorded_at: datetime
    outcome: str
