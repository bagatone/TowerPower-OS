"""Modelli di lettura della BOLLA DI CONSEGNA V1.

La BOLLA non e' una nuova entita' commerciale: e' la vista documentale di una
CONSEGNA gia' governata (tpo.consegne + tpo.righe_consegna), arricchita con la
provenienza di lotto registrata in tpo.consumi_lotto (CONSUMO_LOTTO, vedi
docs/architecture/CONSUMO_LOTTO_AUTHORITY_FREEZE.md). Sola lettura: nessun
dato viene creato o modificato.

Regola di onesta': la parte di una riga che il registro lotti non spiega
(consegne precedenti al registro, giacenza senza origine) compare come
``quantita_senza_origine``; non viene mai attribuita a un codice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from ...domain.identifiers import ConsegnaId
from .errors import InvalidBollaLetturaQueryError


@dataclass(frozen=True)
class RichiediBolla:
    consegna_id: ConsegnaId

    def __post_init__(self) -> None:
        if not isinstance(self.consegna_id, ConsegnaId):
            raise InvalidBollaLetturaQueryError("consegna_id deve essere un ConsegnaId.")


@dataclass(frozen=True)
class OrigineLotto:
    """Quantita' di una riga che proviene da un preciso codice AAA-GGMM-L."""

    codice_tracciabilita: str
    raccolta_id: str
    data_raccolta: datetime
    quantita: Decimal


@dataclass(frozen=True)
class RigaBolla:
    posizione: int
    ordine_id: str
    varieta_id: str
    varieta_denominazione: str
    quantita: Decimal
    unita_misura: str
    rettifica: bool
    origini: tuple[OrigineLotto, ...]
    quantita_senza_origine: Decimal
    # Solo nelle bolle unite (vedi unione.py): da quale CONSEGNA viene la riga e quando e' stata consegnata.
    consegna_origine: str | None = None
    data_consegna_origine: date | None = None
    # Prezzo unitario dal LISTINO_VARIETA (per unita' della riga, IGIC non aggiunta); None = listino senza prezzo.
    prezzo_unitario: Decimal | None = None

    @property
    def importo(self) -> Decimal | None:
        """quantita' x prezzo unitario (come lo calcola l'emissione fattura); None se manca il prezzo."""
        return None if self.prezzo_unitario is None else self.quantita * self.prezzo_unitario


@dataclass(frozen=True)
class PagamentoBolla:
    """Pagamento valido (non annullato) della CONSEGNA, se registrato (PAGAMENTO_CONSEGNA)."""

    pagamento_id: str
    data_pagamento: date
    metodo: str
    importo: Decimal | None
    storico: bool


@dataclass(frozen=True)
class Bolla:
    consegna_id: ConsegnaId
    stato: str
    cliente_id: str
    cliente_denominazione: str
    data_prevista: date
    data_effettiva: datetime | None
    operatore: str | None
    destinazione_fisica: str | None
    righe: tuple[RigaBolla, ...]
    pagamento: PagamentoBolla | None = None
    # Solo nelle bolle unite: tutti i codici CONSEGNA riuniti (consegna_id e' l'ultima).
    consegne_unite: tuple[str, ...] = ()

    @property
    def righe_senza_origine(self) -> int:
        return sum(1 for riga in self.righe if riga.quantita_senza_origine > 0)

    @property
    def ha_prezzi(self) -> bool:
        return any(riga.prezzo_unitario is not None for riga in self.righe)

    @property
    def prezzi_completi(self) -> bool:
        return bool(self.righe) and all(riga.prezzo_unitario is not None for riga in self.righe)

    @property
    def totale(self) -> Decimal | None:
        """Somma degli importi delle righe con prezzo; None se nessuna riga ha il prezzo."""
        if not self.ha_prezzi:
            return None
        return sum((r.importo for r in self.righe if r.importo is not None), Decimal(0))
