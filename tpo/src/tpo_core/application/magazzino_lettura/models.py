"""Contratti immutabili della query MAGAZZINO (sola lettura) V1.

Autorita: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md
(Fase 1, boundary STOCK + MOVIMENTO_MAGAZZINO + ARTICOLO). Query a sola
lettura. Copre due catene di stock distinte: tpo.stock (per VARIETA --
seme/prodotto coltivato) e tpo.stock_articoli (per ARTICOLO -- materiali
della catena: substrati, packaging, ecc., vedi
docs/architecture/ARTICOLO_AUTHORITY_FREEZE.md), piu' il registro
movimenti tpo.movimenti_magazzino, dove ogni riga si riferisce a
ESATTAMENTE una VARIETA o un ARTICOLO (mai entrambi, mai nessuno --
ck_movimenti_magazzino_risorsa_xor a livello DB). Non e' una query di
disponibilita' commerciale (quella e' gia' coperta da
disponibilita_commerciale/STOCK_DISPONIBILITA_COMMERCIALE_FREEZE.md,
che sottrae il PRENOTATO da RIGHE_ORDINE aperte): questa e' la vista
di magazzino grezza, per l'operativita' interna.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from ...domain.identifiers import (
    ArticoloId, ConsegnaId, MovimentoId, RaccoltaId, RunId, VarietaId,
)
from .errors import InvalidMagazzinoLetturaQueryError

TIPI_MOVIMENTO_AMMESSI = frozenset({"CARICO", "SCARICO", "RETTIFICA"})
DIREZIONI_MOVIMENTO_AMMESSE = frozenset({"POSITIVO", "NEGATIVO"})


@dataclass(frozen=True)
class RichiediElencoArticoli:
    """Nessun filtro in V1: elenco completo."""


@dataclass(frozen=True)
class RichiediElencoStock:
    """Nessun filtro in V1: elenco completo (righe VARIETA + righe ARTICOLO)."""


@dataclass(frozen=True)
class RichiediElencoMovimenti:
    """Nessun filtro in V1: elenco completo, ordinato per data_movimento decrescente."""


@dataclass(frozen=True)
class Articolo:
    articolo_id: ArticoloId
    denominazione: str
    unita_misura: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.articolo_id, ArticoloId):
            raise InvalidMagazzinoLetturaQueryError("articolo_id non valido.")
        if not self.denominazione or not self.denominazione.strip():
            raise InvalidMagazzinoLetturaQueryError("denominazione non puo' essere vuota.")


@dataclass(frozen=True)
class ElencoArticoli:
    articoli: tuple[Articolo, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.articoli, tuple):
            raise InvalidMagazzinoLetturaQueryError("articoli deve essere una tupla.")
        for item in self.articoli:
            if not isinstance(item, Articolo):
                raise InvalidMagazzinoLetturaQueryError(
                    "ogni elemento di articoli deve essere un Articolo."
                )


@dataclass(frozen=True)
class StockVarieta:
    varieta_id: VarietaId
    varieta_denominazione: str
    disponibile: Decimal
    unita_misura: str
    updated_at: datetime
    version: int

    def __post_init__(self) -> None:
        if not isinstance(self.varieta_id, VarietaId):
            raise InvalidMagazzinoLetturaQueryError("varieta_id non valido.")
        if self.disponibile < 0:
            raise InvalidMagazzinoLetturaQueryError("disponibile non puo' essere negativo.")
        if self.version < 0:
            raise InvalidMagazzinoLetturaQueryError("version non puo' essere negativa.")


@dataclass(frozen=True)
class StockArticolo:
    articolo_id: ArticoloId
    articolo_denominazione: str
    disponibile: Decimal
    unita_misura: str
    updated_at: datetime
    version: int

    def __post_init__(self) -> None:
        if not isinstance(self.articolo_id, ArticoloId):
            raise InvalidMagazzinoLetturaQueryError("articolo_id non valido.")
        if self.disponibile < 0:
            raise InvalidMagazzinoLetturaQueryError("disponibile non puo' essere negativo.")
        if self.version < 0:
            raise InvalidMagazzinoLetturaQueryError("version non puo' essere negativa.")


@dataclass(frozen=True)
class ElencoStock:
    stock_varieta: tuple[StockVarieta, ...]
    stock_articoli: tuple[StockArticolo, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.stock_varieta, tuple) or not isinstance(self.stock_articoli, tuple):
            raise InvalidMagazzinoLetturaQueryError(
                "stock_varieta e stock_articoli devono essere tuple."
            )
        for item in self.stock_varieta:
            if not isinstance(item, StockVarieta):
                raise InvalidMagazzinoLetturaQueryError(
                    "ogni elemento di stock_varieta deve essere uno StockVarieta."
                )
        for item in self.stock_articoli:
            if not isinstance(item, StockArticolo):
                raise InvalidMagazzinoLetturaQueryError(
                    "ogni elemento di stock_articoli deve essere uno StockArticolo."
                )


@dataclass(frozen=True)
class MovimentoMagazzino:
    movimento_id: MovimentoId
    varieta_id: VarietaId | None
    varieta_denominazione: str | None
    articolo_id: ArticoloId | None
    articolo_denominazione: str | None
    unita_misura: str
    tipo: str
    direzione: str
    quantita: Decimal
    data_movimento: datetime
    motivo: str
    origine_tipo: str
    origine_riferimento: str | None
    raccolta_id: RaccoltaId | None
    consegna_id: ConsegnaId | None
    run_id: RunId | None
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.movimento_id, MovimentoId):
            raise InvalidMagazzinoLetturaQueryError("movimento_id non valido.")
        risorse = [self.varieta_id is not None, self.articolo_id is not None]
        if sum(risorse) != 1:
            raise InvalidMagazzinoLetturaQueryError(
                "un movimento deve riferirsi a esattamente una VARIETA o un ARTICOLO."
            )
        if (self.varieta_id is not None) != (self.varieta_denominazione is not None):
            raise InvalidMagazzinoLetturaQueryError(
                "varieta_denominazione deve essere presente se e solo se varieta_id lo e'."
            )
        if (self.articolo_id is not None) != (self.articolo_denominazione is not None):
            raise InvalidMagazzinoLetturaQueryError(
                "articolo_denominazione deve essere presente se e solo se articolo_id lo e'."
            )
        if self.tipo not in TIPI_MOVIMENTO_AMMESSI:
            raise InvalidMagazzinoLetturaQueryError("tipo non valido.")
        if self.direzione not in DIREZIONI_MOVIMENTO_AMMESSE:
            raise InvalidMagazzinoLetturaQueryError("direzione non valida.")
        if self.quantita <= 0:
            raise InvalidMagazzinoLetturaQueryError("quantita deve essere positiva.")
        if not self.motivo or not self.motivo.strip():
            raise InvalidMagazzinoLetturaQueryError("motivo non puo' essere vuoto.")
        if not self.origine_tipo or not self.origine_tipo.strip():
            raise InvalidMagazzinoLetturaQueryError("origine_tipo non puo' essere vuoto.")


@dataclass(frozen=True)
class ElencoMovimenti:
    movimenti: tuple[MovimentoMagazzino, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.movimenti, tuple):
            raise InvalidMagazzinoLetturaQueryError("movimenti deve essere una tupla.")
        for item in self.movimenti:
            if not isinstance(item, MovimentoMagazzino):
                raise InvalidMagazzinoLetturaQueryError(
                    "ogni elemento di movimenti deve essere un MovimentoMagazzino."
                )
