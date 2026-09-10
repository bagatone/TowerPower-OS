"""Contratti immutabili della query VARIETA/LISTINO_VARIETA (sola lettura) V1.

Autorita: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md
(Fase 1, boundary VARIETA/LISTINO_VARIETA). Query a sola lettura: nessuna
scrittura su tpo.varieta o tpo.listino_varieta. Il prezzo/aliquota sono
opzionali (LISTINO_VARIETA e' una riga 1:1 facoltativa: una VARIETA senza
prezzo impostato non ha ancora una riga in tpo.listino_varieta).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from ...domain.identifiers import VarietaId
from .errors import InvalidVarietaLetturaQueryError

STATI_VARIETA_AMMESSI = frozenset({"ATTIVA", "IN_SPERIMENTAZIONE", "SOSPESA", "DISMESSA"})


@dataclass(frozen=True)
class RichiediVarieta:
    varieta_id: VarietaId

    def __post_init__(self) -> None:
        if not isinstance(self.varieta_id, VarietaId):
            raise InvalidVarietaLetturaQueryError("varieta_id non valido.")


@dataclass(frozen=True)
class RichiediElencoVarieta:
    """Nessun filtro in V1: elenco completo."""


@dataclass(frozen=True)
class Varieta:
    varieta_id: VarietaId
    denominazione: str
    stato: str
    prezzo_unitario: Decimal | None
    aliquota_igic: Decimal | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.varieta_id, VarietaId):
            raise InvalidVarietaLetturaQueryError("varieta_id non valido.")
        if not isinstance(self.denominazione, str) or not self.denominazione.strip():
            raise InvalidVarietaLetturaQueryError("denominazione non valida.")
        if self.stato not in STATI_VARIETA_AMMESSI:
            raise InvalidVarietaLetturaQueryError("stato non valido.")
        if self.prezzo_unitario is not None and self.prezzo_unitario < 0:
            raise InvalidVarietaLetturaQueryError("prezzo_unitario non puo' essere negativo.")
        if self.aliquota_igic is not None and not (
            Decimal(0) <= self.aliquota_igic <= Decimal(100)
        ):
            raise InvalidVarietaLetturaQueryError("aliquota_igic deve essere tra 0 e 100.")
        if (self.prezzo_unitario is None) != (self.aliquota_igic is None):
            raise InvalidVarietaLetturaQueryError(
                "prezzo_unitario e aliquota_igic devono essere entrambi presenti o entrambi assenti."
            )


@dataclass(frozen=True)
class ElencoVarieta:
    varieta: tuple[Varieta, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.varieta, tuple):
            raise InvalidVarietaLetturaQueryError("varieta deve essere una tupla.")
        for item in self.varieta:
            if not isinstance(item, Varieta):
                raise InvalidVarietaLetturaQueryError(
                    "ogni elemento di varieta deve essere una Varieta."
                )
