"""Contratti immutabili del PAGAMENTO CONSEGNA V1 (PAGAMENTO_CONSEGNA_AUTHORITY_FREEZE.md)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib

from ...domain.identifiers import ActorId, ConsegnaId, PagamentoConsegnaId
from ...domain.states import MetodoPagamento
from .errors import (
    InvalidPagamentoConsegnaCommandError, PagamentoConsegnaImportoInvalidoError,
)


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidPagamentoConsegnaCommandError(
            f"{name} deve essere testo normalizzato non vuoto."
        )


@dataclass(frozen=True)
class PagamentoConsegnaAuthority:
    actor: ActorId
    reason: str
    correlation_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidPagamentoConsegnaCommandError("actor non valido.")
        for name, value in (("reason", self.reason), ("correlation_id", self.correlation_id),
                            ("idempotency_key", self.idempotency_key)):
            _text(name, value)


def _importo_facoltativo(value: object) -> Decimal | None:
    """L'importo e' facoltativo: se presente e' positivo, finito, max due decimali."""
    if value is None:
        return None
    if isinstance(value, (float, bool)):
        raise PagamentoConsegnaImportoInvalidoError("importo non accetta float o booleani.")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PagamentoConsegnaImportoInvalidoError("importo deve essere decimale.") from exc
    if not result.is_finite() or result <= 0 or result.as_tuple().exponent < -2:
        raise PagamentoConsegnaImportoInvalidoError(
            "importo deve essere positivo, finito e con massimo due decimali."
        )
    return result


def _metodo(value: object) -> MetodoPagamento:
    if isinstance(value, MetodoPagamento):
        return value
    try:
        return MetodoPagamento(value)
    except (ValueError, TypeError) as exc:
        raise InvalidPagamentoConsegnaCommandError("metodo di pagamento non valido.") from exc


def _frame(value: str | None) -> str:
    return "-1:" if value is None else f"{len(value.encode('utf-8'))}:{value}"


def _decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f").rstrip("0").rstrip(".") or "0"


def _hash(values: tuple) -> str:
    return hashlib.sha256("".join(_frame(v) for v in values).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RegistraPagamentoConsegna:
    consegna_id: ConsegnaId
    data_pagamento: date
    metodo: MetodoPagamento
    authority: PagamentoConsegnaAuthority
    importo: Decimal | None = None
    note: str | None = None
    storico: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.consegna_id, ConsegnaId):
            raise InvalidPagamentoConsegnaCommandError("consegna_id non valido.")
        if isinstance(self.data_pagamento, datetime) or not isinstance(self.data_pagamento, date):
            raise InvalidPagamentoConsegnaCommandError(
                "data_pagamento deve essere una data (non un datetime)."
            )
        object.__setattr__(self, "metodo", _metodo(self.metodo))
        object.__setattr__(self, "importo", _importo_facoltativo(self.importo))
        if not isinstance(self.authority, PagamentoConsegnaAuthority):
            raise InvalidPagamentoConsegnaCommandError("authority non valida.")
        if self.note is not None:
            _text("note", self.note)
        if not isinstance(self.storico, bool):
            raise InvalidPagamentoConsegnaCommandError("storico deve essere booleano.")

    @property
    def canonical_payload_hash(self) -> str:
        return _hash((
            "PAGAMENTO-CONSEGNA-REGISTRA-V1", self.consegna_id.value,
            self.data_pagamento.isoformat(), self.metodo.value, _decimal(self.importo),
            self.note, "1" if self.storico else "0",
        ))


@dataclass(frozen=True)
class RegistraPagamentoConsegnaResult:
    pagamento_id: PagamentoConsegnaId
    consegna_id: ConsegnaId
    data_pagamento: date
    metodo: MetodoPagamento
    importo: Decimal | None
    storico: bool
    recorded_at: datetime
    outcome: str


@dataclass(frozen=True)
class AnnullaPagamentoConsegna:
    pagamento_id: PagamentoConsegnaId
    authority: PagamentoConsegnaAuthority
    note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.pagamento_id, PagamentoConsegnaId):
            raise InvalidPagamentoConsegnaCommandError("pagamento_id non valido.")
        if not isinstance(self.authority, PagamentoConsegnaAuthority):
            raise InvalidPagamentoConsegnaCommandError("authority non valida.")
        if self.note is not None:
            _text("note", self.note)

    @property
    def canonical_payload_hash(self) -> str:
        return _hash(("PAGAMENTO-CONSEGNA-ANNULLA-V1", self.pagamento_id.value, self.note))


@dataclass(frozen=True)
class AnnullaPagamentoConsegnaResult:
    annullamento_id: PagamentoConsegnaId
    pagamento_id: PagamentoConsegnaId
    consegna_id: ConsegnaId
    recorded_at: datetime
    outcome: str
