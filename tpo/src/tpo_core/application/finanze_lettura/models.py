"""Contratti immutabili della query FINANZE (sola lettura) V1: FATTURA,
INCASSO, USCITA.

Autorita: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md
(Fase 1, boundary FATTURA + INCASSO + USCITA). Query a sola lettura.

Scelte di scope deliberate:
- FATTURA usa NumeroFattura (AAAA/NNNN) come identita' pubblica, non un
  PermanentId (Owner Decision D1, docs/architecture/FATTURA_AUTHORITY_FREEZE.md
  Sezione 5 -- vedi src/tpo_core/domain/identifiers.py:NumeroFattura).
- RIGA_FATTURA non risolve il riferimento a RIGA_CONSEGNA (tpo.righe_fattura
  .riga_consegna_id): quella riga non ha un'identita' pubblica stabile
  indipendente e la tracciabilita' fattura->consegna e' gia' esposta a
  livello di FATTURA (consegne_collegate, da tpo.fatture_consegne).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from ...domain.identifiers import ClienteId, ConsegnaId, IncassoId, NumeroFattura, UscitaId, VarietaId
from .errors import InvalidFinanzeLetturaQueryError

METODI_PAGAMENTO_AMMESSI = frozenset({"BONIFICO", "CONTANTI", "CARTA", "BIZUM", "ALTRO"})
CATEGORIE_USCITA_AMMESSE = frozenset(
    {"SEMENTI", "ATTREZZATURA", "AFFITTO", "UTENZE", "STIPENDI", "TRASPORTO", "ALTRO"}
)


@dataclass(frozen=True)
class RichiediElencoFatture:
    """Nessun filtro in V1: elenco completo, ordinato per data_emissione decrescente."""


@dataclass(frozen=True)
class RichiediElencoIncassi:
    """Nessun filtro in V1: elenco completo, ordinato per data_incasso decrescente."""


@dataclass(frozen=True)
class RichiediElencoUscite:
    """Nessun filtro in V1: elenco completo, ordinato per data_uscita decrescente."""


@dataclass(frozen=True)
class RigaFattura:
    posizione: int
    varieta_id: VarietaId
    varieta_denominazione: str
    quantita: Decimal
    unita_misura: str
    prezzo_unitario: Decimal
    aliquota_igic: Decimal
    importo_netto: Decimal
    importo_igic: Decimal

    def __post_init__(self) -> None:
        if self.posizione <= 0:
            raise InvalidFinanzeLetturaQueryError("posizione deve essere positiva.")
        if not isinstance(self.varieta_id, VarietaId):
            raise InvalidFinanzeLetturaQueryError("varieta_id non valido.")
        if self.quantita <= 0:
            raise InvalidFinanzeLetturaQueryError("quantita deve essere positiva.")
        if self.prezzo_unitario < 0:
            raise InvalidFinanzeLetturaQueryError("prezzo_unitario non puo' essere negativo.")
        if not 0 <= self.aliquota_igic <= 100:
            raise InvalidFinanzeLetturaQueryError("aliquota_igic deve essere tra 0 e 100.")


@dataclass(frozen=True)
class Fattura:
    numero_fattura: NumeroFattura
    cliente_id: ClienteId
    cliente_denominazione: str
    data_emissione: date
    scadenza: date
    totale_netto: Decimal
    totale_igic: Decimal
    totale: Decimal
    rettifica_di: NumeroFattura | None
    consegne_collegate: tuple[ConsegnaId, ...]
    righe: tuple[RigaFattura, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.numero_fattura, NumeroFattura):
            raise InvalidFinanzeLetturaQueryError("numero_fattura non valido.")
        if not isinstance(self.cliente_id, ClienteId):
            raise InvalidFinanzeLetturaQueryError("cliente_id non valido.")
        if self.scadenza < self.data_emissione:
            raise InvalidFinanzeLetturaQueryError("scadenza non puo' precedere data_emissione.")
        if self.totale != self.totale_netto + self.totale_igic:
            raise InvalidFinanzeLetturaQueryError(
                "totale deve essere esattamente totale_netto + totale_igic."
            )
        if self.rettifica_di is not None and self.rettifica_di == self.numero_fattura:
            raise InvalidFinanzeLetturaQueryError(
                "rettifica_di non puo' coincidere con numero_fattura."
            )
        if not isinstance(self.consegne_collegate, tuple) or any(
            not isinstance(c, ConsegnaId) for c in self.consegne_collegate
        ):
            raise InvalidFinanzeLetturaQueryError(
                "consegne_collegate deve essere una tupla di ConsegnaId."
            )
        if not isinstance(self.righe, tuple) or any(
            not isinstance(r, RigaFattura) for r in self.righe
        ):
            raise InvalidFinanzeLetturaQueryError("righe deve essere una tupla di RigaFattura.")


@dataclass(frozen=True)
class ElencoFatture:
    fatture: tuple[Fattura, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.fatture, tuple) or any(
            not isinstance(f, Fattura) for f in self.fatture
        ):
            raise InvalidFinanzeLetturaQueryError("fatture deve essere una tupla di Fattura.")


@dataclass(frozen=True)
class Incasso:
    incasso_id: IncassoId
    fattura_numero: NumeroFattura
    importo: Decimal
    data_incasso: date
    metodo: str
    note: str | None
    rettifica_incasso_id: IncassoId | None
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.incasso_id, IncassoId):
            raise InvalidFinanzeLetturaQueryError("incasso_id non valido.")
        if not isinstance(self.fattura_numero, NumeroFattura):
            raise InvalidFinanzeLetturaQueryError("fattura_numero non valido.")
        if self.metodo not in METODI_PAGAMENTO_AMMESSI:
            raise InvalidFinanzeLetturaQueryError("metodo non valido.")
        if self.rettifica_incasso_id is None and self.importo <= 0:
            raise InvalidFinanzeLetturaQueryError(
                "un incasso ordinario deve avere importo positivo."
            )
        if self.rettifica_incasso_id is not None and self.importo == 0:
            raise InvalidFinanzeLetturaQueryError(
                "una rettifica di incasso non puo' avere importo zero."
            )


@dataclass(frozen=True)
class ElencoIncassi:
    incassi: tuple[Incasso, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.incassi, tuple) or any(
            not isinstance(i, Incasso) for i in self.incassi
        ):
            raise InvalidFinanzeLetturaQueryError("incassi deve essere una tupla di Incasso.")


@dataclass(frozen=True)
class Uscita:
    uscita_id: UscitaId
    importo: Decimal
    data_uscita: date
    categoria: str
    beneficiario: str
    metodo: str
    note: str | None
    rettifica_uscita_id: UscitaId | None
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.uscita_id, UscitaId):
            raise InvalidFinanzeLetturaQueryError("uscita_id non valido.")
        if self.categoria not in CATEGORIE_USCITA_AMMESSE:
            raise InvalidFinanzeLetturaQueryError("categoria non valida.")
        if not self.beneficiario or not self.beneficiario.strip():
            raise InvalidFinanzeLetturaQueryError("beneficiario non puo' essere vuoto.")
        if self.metodo not in METODI_PAGAMENTO_AMMESSI:
            raise InvalidFinanzeLetturaQueryError("metodo non valido.")
        if self.rettifica_uscita_id is None and self.importo <= 0:
            raise InvalidFinanzeLetturaQueryError(
                "una uscita ordinaria deve avere importo positivo."
            )
        if self.rettifica_uscita_id is not None and self.importo == 0:
            raise InvalidFinanzeLetturaQueryError(
                "una rettifica di uscita non puo' avere importo zero."
            )


@dataclass(frozen=True)
class ElencoUscite:
    uscite: tuple[Uscita, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.uscite, tuple) or any(
            not isinstance(u, Uscita) for u in self.uscite
        ):
            raise InvalidFinanzeLetturaQueryError("uscite deve essere una tupla di Uscita.")
