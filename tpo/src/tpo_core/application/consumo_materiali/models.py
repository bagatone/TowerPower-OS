"""Contratti del boundary CONSUMO_MATERIALI_SEMINA V1.

Ogni SET seminato consuma materiali di magazzino: ``PEZZI_PER_SET_DEFAULT``
(4) vaschette e altrettanti substrati (1 substrato per vaschetta), regola
della configurazione storica di Matteo (src/init_resource_engine.py). Il
numero di SET NON e' memorizzato sulla SEMINA (che registra i grammi di
seme), quindi e' sempre dichiarato esplicitamente dal chiamante.

Il comando non introduce nuove tabelle: pubblica due MOVIMENTI SCARICO
ARTICOLO tramite il boundary MOVIMENTO_ARTICOLO V1, con idempotency key
derivate da (semina, articolo): una semina non puo' essere contabilizzata due
volte, nemmeno con una chiave diversa fornita dal chiamante.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ...domain.identifiers import ActorId, ArticoloId, SeminaId
from ..movimento_articolo.models import RegistraMovimentoArticoloResult
from .errors import InvalidConsumoMaterialiCommandError

PEZZI_PER_SET_DEFAULT = 4
DENOMINAZIONE_SUBSTRATO_DEFAULT = "Substrato"
DENOMINAZIONE_VASCHETTE_DEFAULT = "Vaschette"


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidConsumoMaterialiCommandError(
            f"{name} deve essere testo normalizzato non vuoto."
        )


@dataclass(frozen=True)
class ConsumoMaterialiAuthority:
    actor: ActorId
    reason: str
    correlation_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidConsumoMaterialiCommandError("actor non valido.")
        _text("reason", self.reason)
        _text("correlation_id", self.correlation_id)


@dataclass(frozen=True)
class RegistraConsumoMaterialiSemina:
    semina_id: SeminaId
    set_seminati: int
    authority: ConsumoMaterialiAuthority
    pezzi_per_set: int = PEZZI_PER_SET_DEFAULT
    articolo_substrato: Optional[ArticoloId] = None
    articolo_vaschette: Optional[ArticoloId] = None
    effective_at: Optional[datetime] = None  # default: data_avvio della semina

    def __post_init__(self) -> None:
        if not isinstance(self.semina_id, SeminaId):
            raise InvalidConsumoMaterialiCommandError("semina_id non valido.")
        for name in ("set_seminati", "pezzi_per_set"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise InvalidConsumoMaterialiCommandError(
                    f"{name} deve essere un intero positivo."
                )
        if not isinstance(self.authority, ConsumoMaterialiAuthority):
            raise InvalidConsumoMaterialiCommandError("authority non valida.")
        for name in ("articolo_substrato", "articolo_vaschette"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, ArticoloId):
                raise InvalidConsumoMaterialiCommandError(f"{name} non valido.")
        if self.effective_at is not None and (
            not isinstance(self.effective_at, datetime)
            or self.effective_at.tzinfo is None
            or self.effective_at.utcoffset() is None
        ):
            raise InvalidConsumoMaterialiCommandError("effective_at deve essere aware.")

    @property
    def pezzi(self) -> int:
        return self.set_seminati * self.pezzi_per_set


@dataclass(frozen=True)
class SeminaPerConsumo:
    semina_id: SeminaId
    codice_tracciabilita: str
    varieta: str
    data_avvio: datetime


@dataclass(frozen=True)
class RegistraConsumoMaterialiSeminaResult:
    semina_id: SeminaId
    codice_tracciabilita: str
    set_seminati: int
    pezzi_per_set: int
    vaschette: RegistraMovimentoArticoloResult
    substrato: RegistraMovimentoArticoloResult
