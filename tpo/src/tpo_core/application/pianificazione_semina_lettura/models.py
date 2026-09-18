"""Contratti immutabili della query "Da seminare" (sola lettura) V1.

Autorita: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md
-- decimo boundary di lettura, stesso governo dei nove originali (vedi
Fatto 18 della roadmap del progetto Claude "TPO system": richiesta
esplicita dell'owner, il calcolo di "cosa seminare" gia' esistente in
Production Planning deve arrivare a una schermata consultabile, non
restare solo interno al database).

Espone esattamente le righe di tpo.righe_piano_semina non ancora avviate
(stato PIANIFICATA/PRONTA/TARDIVA) della revisione CORRENTE di ogni piano
(tpo.piano_produzione_revisioni.sostituita_at IS NULL). Nessun filtro
temporale: Owner Decision esplicita (18/9/2026) di mostrare tutto il non
ancora seminato, non solo un orizzonte di N giorni. Nessun nuovo calcolo
e' introdotto qui: si legge soltanto l'output gia' scritto da
ProductionPlanningEngine/PostgreSQLProductionPlanningCommitWriter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from ...domain.identifiers import ClienteId, RigaPianoSeminaId, VarietaId
from .errors import InvalidPianificazioneSeminaLetturaQueryError

STATI_DA_SEMINARE_AMMESSI = frozenset({"PIANIFICATA", "PRONTA", "TARDIVA"})
_UNITA_MISURA_AMMESSE = frozenset({"SET", "GRAM", "UNIT"})


@dataclass(frozen=True)
class RichiediElencoDaSeminare:
    """Nessun filtro in V1: tutte le righe non ancora avviate della
    revisione corrente, senza limite temporale (Owner Decision 18/9/2026)."""


@dataclass(frozen=True)
class RigaDaSeminare:
    riga_id: RigaPianoSeminaId
    varieta_id: VarietaId
    varieta_denominazione: str
    cliente_id: ClienteId
    cliente_denominazione: str
    stato: str
    quantita_da_seminare: Decimal
    unita_misura: str
    grammi_seme_richiesti: Decimal
    sowing_at: datetime
    harvest_target_at: datetime
    data_consegna: date

    def __post_init__(self) -> None:
        if not isinstance(self.riga_id, RigaPianoSeminaId):
            raise InvalidPianificazioneSeminaLetturaQueryError("riga_id non valido.")
        if not isinstance(self.varieta_id, VarietaId):
            raise InvalidPianificazioneSeminaLetturaQueryError("varieta_id non valido.")
        if not isinstance(self.cliente_id, ClienteId):
            raise InvalidPianificazioneSeminaLetturaQueryError("cliente_id non valido.")
        if not isinstance(self.varieta_denominazione, str) or not self.varieta_denominazione.strip():
            raise InvalidPianificazioneSeminaLetturaQueryError("varieta_denominazione non valida.")
        if not isinstance(self.cliente_denominazione, str) or not self.cliente_denominazione.strip():
            raise InvalidPianificazioneSeminaLetturaQueryError("cliente_denominazione non valida.")
        if self.stato not in STATI_DA_SEMINARE_AMMESSI:
            raise InvalidPianificazioneSeminaLetturaQueryError(
                "stato non ammesso per Da seminare."
            )
        if self.quantita_da_seminare <= 0:
            raise InvalidPianificazioneSeminaLetturaQueryError(
                "quantita_da_seminare deve essere positiva."
            )
        if self.unita_misura not in _UNITA_MISURA_AMMESSE:
            raise InvalidPianificazioneSeminaLetturaQueryError("unita_misura non valida.")
        if self.grammi_seme_richiesti <= 0:
            raise InvalidPianificazioneSeminaLetturaQueryError(
                "grammi_seme_richiesti deve essere positivo."
            )


@dataclass(frozen=True)
class ElencoDaSeminare:
    righe: tuple[RigaDaSeminare, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.righe, tuple):
            raise InvalidPianificazioneSeminaLetturaQueryError("righe deve essere una tupla.")
        for riga in self.righe:
            if not isinstance(riga, RigaDaSeminare):
                raise InvalidPianificazioneSeminaLetturaQueryError(
                    "ogni elemento di righe deve essere una RigaDaSeminare."
                )
