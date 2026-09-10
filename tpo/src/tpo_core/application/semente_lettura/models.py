"""Contratti immutabili della query SEMENTE/LOTTO_SEME (sola lettura) V1.

Autorita: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md
(Fase 1, boundary SEMENTE/SEMENTE_IMPIEGO/LOTTO_SEME). Query a sola
lettura. tpo.sementi non ha identita' pubblica (nessun public_id nello
schema Core: e' referenziata solo per id interno) -- esposta con il suo
id numerico. tpo.lotti_seme ha invece identita' pubblica LSE-######.
SEMENTE_IMPIEGO (raccomandazioni/rating per cultivar-uso) e' fuori da
questo primo giro: aggiunge join su cultivar/cultivar_usi/usi_produttivi
non ancora coperti da un boundary di lettura proprio -- deliberatamente
rimandato, non dimenticato (vedi report a Giulia).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from ...domain.identifiers import LottoSemeId
from .errors import InvalidSementeLetturaQueryError


@dataclass(frozen=True)
class RichiediElencoSementi:
    """Nessun filtro in V1: elenco completo del catalogo fornitori/sementi."""


@dataclass(frozen=True)
class Semente:
    semente_id: int
    fornitore: str
    referenza_commerciale: str
    marca: str | None
    trattamento: str | None
    attiva: bool

    def __post_init__(self) -> None:
        if not isinstance(self.semente_id, int) or self.semente_id <= 0:
            raise InvalidSementeLetturaQueryError("semente_id non valido.")
        if not isinstance(self.fornitore, str) or not self.fornitore.strip():
            raise InvalidSementeLetturaQueryError("fornitore non valido.")
        if not isinstance(self.referenza_commerciale, str) or not self.referenza_commerciale.strip():
            raise InvalidSementeLetturaQueryError("referenza_commerciale non valida.")


@dataclass(frozen=True)
class ElencoSementi:
    sementi: tuple[Semente, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.sementi, tuple):
            raise InvalidSementeLetturaQueryError("sementi deve essere una tupla.")
        for item in self.sementi:
            if not isinstance(item, Semente):
                raise InvalidSementeLetturaQueryError(
                    "ogni elemento di sementi deve essere una Semente."
                )


@dataclass(frozen=True)
class RichiediLotto:
    lotto_seme_id: LottoSemeId

    def __post_init__(self) -> None:
        if not isinstance(self.lotto_seme_id, LottoSemeId):
            raise InvalidSementeLetturaQueryError("lotto_seme_id non valido.")


@dataclass(frozen=True)
class RichiediElencoLotti:
    """Nessun filtro in V1: elenco completo dei lotti seme."""


@dataclass(frozen=True)
class LottoSeme:
    lotto_seme_id: LottoSemeId
    semente_fornitore: str
    semente_referenza_commerciale: str
    numero_lotto_produttore: str
    data_ricezione: date
    data_scadenza: date | None
    quantita_iniziale: Decimal
    quantita_residua: Decimal
    unita_misura: str
    anomalia: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.lotto_seme_id, LottoSemeId):
            raise InvalidSementeLetturaQueryError("lotto_seme_id non valido.")
        if self.quantita_iniziale <= 0:
            raise InvalidSementeLetturaQueryError("quantita_iniziale deve essere positiva.")
        if not (Decimal(0) <= self.quantita_residua <= self.quantita_iniziale):
            raise InvalidSementeLetturaQueryError(
                "quantita_residua deve essere tra 0 e quantita_iniziale."
            )
        if self.data_scadenza is not None and self.data_scadenza < self.data_ricezione:
            raise InvalidSementeLetturaQueryError(
                "data_scadenza non puo' precedere data_ricezione."
            )


@dataclass(frozen=True)
class ElencoLotti:
    lotti: tuple[LottoSeme, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.lotti, tuple):
            raise InvalidSementeLetturaQueryError("lotti deve essere una tupla.")
        for item in self.lotti:
            if not isinstance(item, LottoSeme):
                raise InvalidSementeLetturaQueryError(
                    "ogni elemento di lotti deve essere un LottoSeme."
                )
