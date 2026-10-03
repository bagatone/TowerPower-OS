"""Contratti immutabili del boundary ORDINE_MANUALE V1.

Gli ORDINI nascono normalmente dalla pianificazione (PROGRAMMA_FORNITURA ->
RUN, ``tipo_creazione='AUTOMATICO'``). Questo boundary registra l'eccezione:
un ORDINE ``MANUALE`` (vendita extra, richiesta fuori programma) di un CLIENTE
esistente, con righe SET/GRAM di VARIETA attive, senza RUN, programma ne'
chiave idempotente di piano (vincolo ck_ordini_tipo_creazione_metadati). Non
consegna nulla: la CONSEGNA resta il solo fatto che muove lo STOCK.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib

from ...domain.identifiers import ActorId, ClienteId, OrdineId, RigaOrdineId, VarietaId
from ...domain.quantities import UnitOfMeasure
from .errors import InvalidOrdineManualeCommandError

ORDINE_UNITS = frozenset({UnitOfMeasure.GRAM, UnitOfMeasure.SET})


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidOrdineManualeCommandError(
            f"{name} deve essere testo normalizzato non vuoto."
        )


def _frame(value: str) -> str:
    return f"{len(value.encode('utf-8'))}:{value}"


def _decimal(value: Decimal) -> str:
    normalized = format(value, "f").rstrip("0").rstrip(".")
    return normalized or "0"


@dataclass(frozen=True)
class OrdineManualeAuthority:
    actor: ActorId
    reason: str
    correlation_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidOrdineManualeCommandError("actor non valido.")
        for name, value in (("reason", self.reason), ("correlation_id", self.correlation_id),
                            ("idempotency_key", self.idempotency_key)):
            _text(name, value)


@dataclass(frozen=True)
class RigaOrdineManuale:
    varieta_id: VarietaId
    quantita: Decimal
    unita_misura: UnitOfMeasure

    def __post_init__(self) -> None:
        if not isinstance(self.varieta_id, VarietaId):
            raise InvalidOrdineManualeCommandError("varieta_id non valido.")
        if isinstance(self.quantita, (float, bool)) or not isinstance(self.quantita, Decimal):
            raise InvalidOrdineManualeCommandError("quantita deve essere un Decimal.")
        if (not self.quantita.is_finite() or self.quantita <= 0
                or self.quantita.as_tuple().exponent < -6):
            raise InvalidOrdineManualeCommandError(
                "quantita deve essere positiva, finita e con massimo sei decimali."
            )
        if self.unita_misura not in ORDINE_UNITS:
            raise InvalidOrdineManualeCommandError("unita_misura deve essere GRAM o SET.")


@dataclass(frozen=True)
class RegistraOrdineManuale:
    client_id: ClienteId
    data_ordine: date
    data_consegna_prevista: date | None
    righe: tuple[RigaOrdineManuale, ...]
    authority: OrdineManualeAuthority

    def __post_init__(self) -> None:
        if not isinstance(self.client_id, ClienteId):
            raise InvalidOrdineManualeCommandError("client_id non valido.")
        for name, value in (("data_ordine", self.data_ordine),
                            ("data_consegna_prevista", self.data_consegna_prevista)):
            if value is None and name == "data_consegna_prevista":
                continue
            if not isinstance(value, date) or isinstance(value, datetime):
                raise InvalidOrdineManualeCommandError(f"{name} deve essere una data.")
        if (self.data_consegna_prevista is not None
                and self.data_consegna_prevista < self.data_ordine):
            raise InvalidOrdineManualeCommandError(
                "data_consegna_prevista non puo' precedere data_ordine."
            )
        if not isinstance(self.righe, tuple) or not self.righe:
            raise InvalidOrdineManualeCommandError("righe deve essere una tuple non vuota.")
        if any(not isinstance(riga, RigaOrdineManuale) for riga in self.righe):
            raise InvalidOrdineManualeCommandError("righe contiene elementi non validi.")
        if len({riga.varieta_id.value for riga in self.righe}) != len(self.righe):
            raise InvalidOrdineManualeCommandError(
                "Una VARIETA puo' comparire una sola volta per ORDINE."
            )
        if not isinstance(self.authority, OrdineManualeAuthority):
            raise InvalidOrdineManualeCommandError("authority non valida.")

    @property
    def canonical_payload(self) -> str:
        values = [
            "ORDINE-MANUALE-V1", self.client_id.value, self.data_ordine.isoformat(),
            "" if self.data_consegna_prevista is None else self.data_consegna_prevista.isoformat(),
        ]
        for riga in self.righe:
            values += [riga.varieta_id.value, _decimal(riga.quantita), riga.unita_misura.value]
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RigaOrdineRegistrata:
    riga_id: RigaOrdineId
    posizione: int
    varieta_id: VarietaId
    quantita: Decimal
    unita_misura: UnitOfMeasure


@dataclass(frozen=True)
class RegistraOrdineManualeResult:
    ordine_id: OrdineId
    client_id: ClienteId
    stato: str
    version: int
    righe: tuple[RigaOrdineRegistrata, ...]
    outcome: str
