"""Contratti immutabili della query SEMINA/RACCOLTA (sola lettura) V1.

Autorita: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md
(Fase 1, boundary SEMINA + RACCOLTA). Query a sola lettura. Espone lo
stato corrente della SEMINA (tpo.semine.stato) e non lo storico completo
delle transizioni (tpo.semina_lifecycle_eventi) -- deliberatamente
rimandato, non dimenticato. RACCOLTA e' in SET (ck_raccolte_uom_set),
SEMINA e' in GRAM di seme (ck_semine_uom_gram): unita' diverse per stadi
diversi del ciclo, non un'incoerenza.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from ...domain.identifiers import RaccoltaId, SeminaId, VarietaId
from .errors import InvalidSeminaRaccoltaLetturaQueryError

STATI_SEMINA_AMMESSI = frozenset(
    {"AVVIATA", "GERMINAZIONE", "LUCE", "CRESCITA", "PRONTA_ALLA_RACCOLTA", "CHIUSA"}
)
ESITI_SEMINA_AMMESSI = frozenset(
    {"RACCOLTA_COMPLETA", "RACCOLTA_PARZIALE_CON_SCARTO", "SCARTO_TOTALE", "INTERRUZIONE"}
)


@dataclass(frozen=True)
class RichiediSemina:
    semina_id: SeminaId

    def __post_init__(self) -> None:
        if not isinstance(self.semina_id, SeminaId):
            raise InvalidSeminaRaccoltaLetturaQueryError("semina_id non valido.")


@dataclass(frozen=True)
class RichiediElencoSemine:
    """Nessun filtro in V1: elenco completo."""


@dataclass(frozen=True)
class Raccolta:
    raccolta_id: RaccoltaId
    semina_id: SeminaId
    data_raccolta: datetime
    quantita: Decimal
    unita_misura: str
    operatore: str | None
    destinazione_prevista: str | None
    note: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.raccolta_id, RaccoltaId):
            raise InvalidSeminaRaccoltaLetturaQueryError("raccolta_id non valido.")
        if not isinstance(self.semina_id, SeminaId):
            raise InvalidSeminaRaccoltaLetturaQueryError("semina_id non valido.")
        if self.quantita <= 0:
            raise InvalidSeminaRaccoltaLetturaQueryError("quantita deve essere positiva.")


@dataclass(frozen=True)
class Semina:
    semina_id: SeminaId
    varieta_id: VarietaId
    varieta_denominazione: str
    stato: str
    quantita_seme: Decimal
    unita_misura: str
    data_avvio: datetime
    causa_origine: str
    esito_finale: str | None
    cultivar_snapshot: str
    lotto_seme_snapshot: str
    raccolte: tuple[Raccolta, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.semina_id, SeminaId):
            raise InvalidSeminaRaccoltaLetturaQueryError("semina_id non valido.")
        if self.stato not in STATI_SEMINA_AMMESSI:
            raise InvalidSeminaRaccoltaLetturaQueryError("stato non valido.")
        if self.esito_finale is not None and self.esito_finale not in ESITI_SEMINA_AMMESSI:
            raise InvalidSeminaRaccoltaLetturaQueryError("esito_finale non valido.")
        if (self.stato == "CHIUSA") != (self.esito_finale is not None):
            raise InvalidSeminaRaccoltaLetturaQueryError(
                "esito_finale deve essere presente se e solo se stato e' CHIUSA."
            )
        if self.quantita_seme <= 0:
            raise InvalidSeminaRaccoltaLetturaQueryError("quantita_seme deve essere positiva.")
        if not isinstance(self.raccolte, tuple):
            raise InvalidSeminaRaccoltaLetturaQueryError("raccolte deve essere una tupla.")
        for raccolta in self.raccolte:
            if not isinstance(raccolta, Raccolta):
                raise InvalidSeminaRaccoltaLetturaQueryError(
                    "ogni elemento di raccolte deve essere una Raccolta."
                )
            if raccolta.semina_id != self.semina_id:
                raise InvalidSeminaRaccoltaLetturaQueryError(
                    "ogni Raccolta deve appartenere alla SEMINA richiesta."
                )


@dataclass(frozen=True)
class ElencoSemine:
    semine: tuple[Semina, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.semine, tuple):
            raise InvalidSeminaRaccoltaLetturaQueryError("semine deve essere una tupla.")
        for item in self.semine:
            if not isinstance(item, Semina):
                raise InvalidSeminaRaccoltaLetturaQueryError(
                    "ogni elemento di semine deve essere una Semina."
                )
