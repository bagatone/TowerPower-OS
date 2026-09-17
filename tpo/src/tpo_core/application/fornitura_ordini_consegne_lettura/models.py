"""Contratti immutabili della query FORNITURA/ORDINI/CONSEGNE (sola lettura) V1.

Autorita: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md
(Fase 1, boundary PROGRAMMI_FORNITURA + ORDINI + CONSEGNA +
ASSEGNAZIONE_FISICA). Query a sola lettura.

Scelte di scope deliberate (non dimenticanze):
- PROGRAMMA_FORNITURA espone solo la versione CORRENTE
  (tpo.programmi_fornitura_versioni.valida_al IS NULL, garantito unico da
  uq_programmi_fornitura_versioni_corrente). Lo storico delle versioni
  precedenti non e' esposto in V1. Un programma senza versione corrente
  (interamente storicizzato) non compare nell'elenco.
- RIGA_ORDINE e RIGA_CONSEGNA non hanno un'identita' pubblica stabile e
  sempre presente (tpo.righe_ordine.public_id e' nullable e popolato solo
  per righe originate dalla pianificazione produzione). Sono quindi
  referenziate dalla loro chiave naturale (ordine/consegna + posizione),
  mai da un id inventato qui.
- RIGA_CONSEGNA di correzione (rettifica_riga_consegna_id non NULL,
  quantita puo' essere negativa: ck_righe_consegna_ordinary_or_correction)
  e' esposta con un flag e_rettifica, senza risolvere il riferimento alla
  riga originale corretta -- fuori scope V1.
- ORIGINI_RIGHE_ORDINE (tracciabilita' riga_ordine -> riga_programma) non
  e' esposta in V1.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from ...domain.identifiers import (
    AssegnazioneFisicaId, ClienteId, ConsegnaId, OrdineId, ProgrammaFornituraId,
    RaccoltaId, VarietaId,
)
from .errors import InvalidFornituraOrdiniConsegneLetturaQueryError

STATI_PROGRAMMA_FORNITURA_AMMESSI = frozenset({"ATTIVO", "SOSPESO", "TERMINATO"})
TIPI_RICORRENZA_AMMESSI = frozenset(
    {"SETTIMANALE", "QUINDICINALE", "MENSILE", "OGNI_X_GIORNI", "GIORNI_SETTIMANA"}
)
STATI_ORDINE_AMMESSI = frozenset({"APERTO", "PARZIALMENTE_EVASO", "EVASO", "ANNULLATO"})
TIPI_CREAZIONE_ORDINE_AMMESSI = frozenset({"AUTOMATICO", "MANUALE"})
STATI_CONSEGNA_AMMESSI = frozenset({"PROGRAMMATA", "IN_PREPARAZIONE", "CONSEGNATA", "ANNULLATA"})


@dataclass(frozen=True)
class RichiediElencoProgrammiFornitura:
    """Nessun filtro in V1: solo i programmi con versione corrente attiva."""


@dataclass(frozen=True)
class RichiediElencoOrdini:
    """Nessun filtro in V1: elenco completo, ordinato per data_ordine decrescente."""


@dataclass(frozen=True)
class RichiediElencoConsegne:
    """Nessun filtro in V1: elenco completo, ordinato per data_prevista decrescente."""


@dataclass(frozen=True)
class RichiediElencoAssegnazioniFisiche:
    """Nessun filtro in V1: elenco completo."""


@dataclass(frozen=True)
class RigaProgrammaFornitura:
    posizione: int
    varieta_id: VarietaId
    varieta_denominazione: str
    quantita: Decimal
    unita_misura: str
    tipo_ricorrenza: str
    intervallo_giorni: int | None
    giorni_settimana: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.posizione <= 0:
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("posizione deve essere positiva.")
        if not isinstance(self.varieta_id, VarietaId):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("varieta_id non valido.")
        if self.quantita <= 0:
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("quantita deve essere positiva.")
        if self.tipo_ricorrenza not in TIPI_RICORRENZA_AMMESSI:
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("tipo_ricorrenza non valido.")
        if (self.tipo_ricorrenza == "OGNI_X_GIORNI") != (self.intervallo_giorni is not None):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError(
                "intervallo_giorni deve essere presente se e solo se tipo_ricorrenza e' OGNI_X_GIORNI."
            )
        for giorno in self.giorni_settimana:
            if not 1 <= giorno <= 7:
                raise InvalidFornituraOrdiniConsegneLetturaQueryError(
                    "giorni_settimana deve contenere solo valori ISO 1-7."
                )


@dataclass(frozen=True)
class ProgrammaFornitura:
    programma_id: ProgrammaFornituraId
    cliente_id: ClienteId
    cliente_denominazione: str
    numero_versione: int
    stato: str
    data_inizio: date
    data_fine: date | None
    finestra_operativa_giorni: int
    valida_dal: datetime
    righe: tuple[RigaProgrammaFornitura, ...]
    data_ripresa_prevista: date | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.programma_id, ProgrammaFornituraId):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("programma_id non valido.")
        if not isinstance(self.cliente_id, ClienteId):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("cliente_id non valido.")
        if self.numero_versione <= 0:
            raise InvalidFornituraOrdiniConsegneLetturaQueryError(
                "numero_versione deve essere positiva."
            )
        if self.stato not in STATI_PROGRAMMA_FORNITURA_AMMESSI:
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("stato non valido.")
        if self.data_fine is not None and self.data_fine < self.data_inizio:
            raise InvalidFornituraOrdiniConsegneLetturaQueryError(
                "data_fine non puo' precedere data_inizio."
            )
        if self.finestra_operativa_giorni < 0:
            raise InvalidFornituraOrdiniConsegneLetturaQueryError(
                "finestra_operativa_giorni non puo' essere negativa."
            )
        if self.data_ripresa_prevista is not None and (
            not isinstance(self.data_ripresa_prevista, date)
            or isinstance(self.data_ripresa_prevista, datetime)
        ):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError(
                "data_ripresa_prevista deve essere una date valida, se presente."
            )
        if not isinstance(self.righe, tuple) or any(
            not isinstance(r, RigaProgrammaFornitura) for r in self.righe
        ):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError(
                "righe deve essere una tupla di RigaProgrammaFornitura."
            )


@dataclass(frozen=True)
class ElencoProgrammiFornitura:
    programmi: tuple[ProgrammaFornitura, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.programmi, tuple) or any(
            not isinstance(p, ProgrammaFornitura) for p in self.programmi
        ):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError(
                "programmi deve essere una tupla di ProgrammaFornitura."
            )


@dataclass(frozen=True)
class RigaOrdine:
    posizione: int
    varieta_id: VarietaId
    varieta_denominazione: str
    quantita: Decimal
    unita_misura: str

    def __post_init__(self) -> None:
        if self.posizione <= 0:
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("posizione deve essere positiva.")
        if not isinstance(self.varieta_id, VarietaId):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("varieta_id non valido.")
        if self.quantita <= 0:
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("quantita deve essere positiva.")


@dataclass(frozen=True)
class Ordine:
    ordine_id: OrdineId
    cliente_id: ClienteId
    cliente_denominazione: str
    programma_fornitura_id: ProgrammaFornituraId | None
    data_ordine: date
    data_consegna_prevista: date | None
    stato: str
    tipo_creazione: str
    righe: tuple[RigaOrdine, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.ordine_id, OrdineId):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("ordine_id non valido.")
        if not isinstance(self.cliente_id, ClienteId):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("cliente_id non valido.")
        if self.stato not in STATI_ORDINE_AMMESSI:
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("stato non valido.")
        if self.tipo_creazione not in TIPI_CREAZIONE_ORDINE_AMMESSI:
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("tipo_creazione non valido.")
        if (
            self.data_consegna_prevista is not None
            and self.data_consegna_prevista < self.data_ordine
        ):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError(
                "data_consegna_prevista non puo' precedere data_ordine."
            )
        if not isinstance(self.righe, tuple) or any(
            not isinstance(r, RigaOrdine) for r in self.righe
        ):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError(
                "righe deve essere una tupla di RigaOrdine."
            )


@dataclass(frozen=True)
class ElencoOrdini:
    ordini: tuple[Ordine, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.ordini, tuple) or any(
            not isinstance(o, Ordine) for o in self.ordini
        ):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError(
                "ordini deve essere una tupla di Ordine."
            )


@dataclass(frozen=True)
class RigaConsegna:
    posizione: int
    varieta_id: VarietaId
    varieta_denominazione: str
    quantita: Decimal
    unita_misura: str
    e_rettifica: bool

    def __post_init__(self) -> None:
        if self.posizione <= 0:
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("posizione deve essere positiva.")
        if not isinstance(self.varieta_id, VarietaId):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("varieta_id non valido.")
        if self.quantita == 0:
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("quantita non puo' essere zero.")


@dataclass(frozen=True)
class Consegna:
    consegna_id: ConsegnaId
    cliente_id: ClienteId
    cliente_denominazione: str
    stato: str
    data_prevista: date
    data_effettiva: datetime | None
    destinazione_fisica: str | None
    ordini_collegati: tuple[OrdineId, ...]
    righe: tuple[RigaConsegna, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.consegna_id, ConsegnaId):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("consegna_id non valido.")
        if not isinstance(self.cliente_id, ClienteId):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("cliente_id non valido.")
        if self.stato not in STATI_CONSEGNA_AMMESSI:
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("stato non valido.")
        if not isinstance(self.ordini_collegati, tuple) or any(
            not isinstance(o, OrdineId) for o in self.ordini_collegati
        ):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError(
                "ordini_collegati deve essere una tupla di OrdineId."
            )
        if not isinstance(self.righe, tuple) or any(
            not isinstance(r, RigaConsegna) for r in self.righe
        ):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError(
                "righe deve essere una tupla di RigaConsegna."
            )


@dataclass(frozen=True)
class ElencoConsegne:
    consegne: tuple[Consegna, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.consegne, tuple) or any(
            not isinstance(c, Consegna) for c in self.consegne
        ):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError(
                "consegne deve essere una tupla di Consegna."
            )


@dataclass(frozen=True)
class AssegnazioneFisica:
    assegnazione_id: AssegnazioneFisicaId
    raccolta_id: RaccoltaId
    ordine_id: OrdineId
    riga_ordine_posizione: int
    consegna_id: ConsegnaId | None
    quantita_assegnata: Decimal
    unita_misura: str
    effective_at: datetime
    motivo: str

    def __post_init__(self) -> None:
        if not isinstance(self.assegnazione_id, AssegnazioneFisicaId):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("assegnazione_id non valido.")
        if not isinstance(self.raccolta_id, RaccoltaId):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("raccolta_id non valido.")
        if not isinstance(self.ordine_id, OrdineId):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("ordine_id non valido.")
        if self.riga_ordine_posizione <= 0:
            raise InvalidFornituraOrdiniConsegneLetturaQueryError(
                "riga_ordine_posizione deve essere positiva."
            )
        if self.quantita_assegnata <= 0:
            raise InvalidFornituraOrdiniConsegneLetturaQueryError(
                "quantita_assegnata deve essere positiva."
            )
        if not self.motivo or not self.motivo.strip():
            raise InvalidFornituraOrdiniConsegneLetturaQueryError("motivo non puo' essere vuoto.")


@dataclass(frozen=True)
class ElencoAssegnazioniFisiche:
    assegnazioni: tuple[AssegnazioneFisica, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.assegnazioni, tuple) or any(
            not isinstance(a, AssegnazioneFisica) for a in self.assegnazioni
        ):
            raise InvalidFornituraOrdiniConsegneLetturaQueryError(
                "assegnazioni deve essere una tupla di AssegnazioneFisica."
            )
