"""Serializzazione generica dei modelli applicativi (sola lettura) per il
web adapter.

Autorità: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md,
Owner Decision D3 -- il web adapter espone esattamente i campi già presenti
nei modelli applicativi dei 10 boundary di lettura Fase 1, senza inventare
o aggiungere alcun campo. `to_jsonable` converte ricorsivamente una
dataclass applicativa (o una tupla/mappa di dataclass) in una struttura
fatta solo di tipi nativi JSON, così che sia la risposta JSON sia la
pagina HTML siano generate dalla stessa unica conversione.
"""
from __future__ import annotations

import dataclasses
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from ..domain.identifiers import ActorId, NumeroFattura, PermanentId

# Value object che si serializzano come stringa (la loro identità pubblica),
# non come dataclass da espandere campo per campo.
_LEAF_VALUE_TYPES = (PermanentId, NumeroFattura, ActorId)


def to_jsonable(value: Any) -> Any:
    """Converte ricorsivamente un valore applicativo in una struttura sicura
    per json.dumps (e riusabile, invariata, per il rendering HTML)."""

    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Decimal):
        # Stringa, non float: preserva esattamente la precisione del dato
        # applicativo (quantità/importi non sono mai binari-approssimati).
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, _LEAF_VALUE_TYPES):
        return str(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    raise TypeError(f"Tipo non serializzabile dal web adapter: {type(value)!r}")
