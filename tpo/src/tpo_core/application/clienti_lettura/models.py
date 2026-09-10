"""Contratti immutabili della query CLIENTI (sola lettura) V1.

Autorita: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md
(Fase 1, boundary CLIENTI). Query a sola lettura: nessuna scrittura su
tpo.clienti. Espone esattamente i campi presenti in tpo.clienti oggi
(id, public_id, denominazione, modalita_fatturazione,
termini_pagamento_giorni, created_at/by, updated_at/by, version) -- nessun
campo aggiuntivo (indirizzo, contatti, stato_relazione, ecc.) e' presente
nello schema Core attuale: se servono, richiedono una loro Owner Decision
e un'estensione dello schema, non un'invenzione qui.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ...domain.identifiers import ClienteId
from .errors import InvalidClientiLetturaQueryError

_MODALITA_FATTURAZIONE_AMMESSE = frozenset({"A_CONSEGNA", "PERIODICA_MENSILE"})


@dataclass(frozen=True)
class RichiediCliente:
    cliente_id: ClienteId

    def __post_init__(self) -> None:
        if not isinstance(self.cliente_id, ClienteId):
            raise InvalidClientiLetturaQueryError("cliente_id non valido.")


@dataclass(frozen=True)
class RichiediElencoClienti:
    """Nessun filtro in V1: elenco completo (il numero di clienti reali di
    Tower Power e' piccolo; paginazione rimandata a richiesta futura)."""


@dataclass(frozen=True)
class Cliente:
    cliente_id: ClienteId
    denominazione: str
    modalita_fatturazione: str | None
    termini_pagamento_giorni: int | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.cliente_id, ClienteId):
            raise InvalidClientiLetturaQueryError("cliente_id non valido.")
        if not isinstance(self.denominazione, str) or not self.denominazione.strip():
            raise InvalidClientiLetturaQueryError("denominazione non valida.")
        if (
            self.modalita_fatturazione is not None
            and self.modalita_fatturazione not in _MODALITA_FATTURAZIONE_AMMESSE
        ):
            raise InvalidClientiLetturaQueryError("modalita_fatturazione non valida.")
        if self.termini_pagamento_giorni is not None and self.termini_pagamento_giorni <= 0:
            raise InvalidClientiLetturaQueryError("termini_pagamento_giorni deve essere positivo.")


@dataclass(frozen=True)
class ElencoClienti:
    clienti: tuple[Cliente, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.clienti, tuple):
            raise InvalidClientiLetturaQueryError("clienti deve essere una tupla.")
        for cliente in self.clienti:
            if not isinstance(cliente, Cliente):
                raise InvalidClientiLetturaQueryError(
                    "ogni elemento di clienti deve essere un Cliente."
                )
