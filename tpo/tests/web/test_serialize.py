"""Unit test di `to_jsonable`: nessun campo inventato, nessuna perdita di
precisione sui Decimal, identificativi resi come stringa (la loro identità
pubblica)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from src.tpo_core.domain.identifiers import ClienteId, NumeroFattura
from src.tpo_core.web.serialize import to_jsonable

from . import factories as f


def test_scalari_passano_invariati() -> None:
    assert to_jsonable(None) is None
    assert to_jsonable(True) is True
    assert to_jsonable(42) == 42
    assert to_jsonable("ciao") == "ciao"


def test_decimal_diventa_stringa_esatta() -> None:
    assert to_jsonable(Decimal("12.50")) == "12.50"


def test_date_e_datetime_diventano_isoformat() -> None:
    assert to_jsonable(date(2026, 9, 7)) == "2026-09-07"
    valore = datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc)
    assert to_jsonable(valore) == valore.isoformat()


def test_identificativi_diventano_la_loro_stringa_pubblica() -> None:
    assert to_jsonable(ClienteId("CLI-000001")) == "CLI-000001"
    assert to_jsonable(NumeroFattura("2026/0001")) == "2026/0001"


def test_dataclass_diventa_dict_con_esattamente_i_suoi_campi() -> None:
    cliente = f.cliente()
    result = to_jsonable(cliente)
    assert isinstance(result, dict)
    assert set(result.keys()) == {
        "cliente_id", "denominazione", "modalita_fatturazione",
        "termini_pagamento_giorni", "created_at", "updated_at",
    }
    assert result["cliente_id"] == "CLI-000001"


def test_tupla_di_dataclass_annidate_si_espande_ricorsivamente() -> None:
    semina = f.semina()
    result = to_jsonable(semina)
    assert isinstance(result["raccolte"], list)
    assert result["raccolte"][0]["raccolta_id"] == "RAC-000001"
    assert result["raccolte"][0]["semina_id"] == result["semina_id"]


def test_mappa_context_di_run_log_voce_si_serializza() -> None:
    voce = f.run_log().voci[0]
    result = to_jsonable(voce)
    assert result["context"] == {}
