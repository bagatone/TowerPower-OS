"""Test del modulo diario_web/rendiconto.py -- solo la logica pura di
risoluzione stock/consegna (`_risolvi_consegne`), senza toccare un database
reale, stesso principio di isolamento gia' applicato in test_actions.py.
La query SQL stessa (`_SELECT_RESIDUO_ORDINI_OGGI`, che calcola il residuo
gia' a livello database sottraendo le consegne CONSEGNATA) non e' duplicata
qui: resta coperta solo da un test di integrazione Postgres reale, non
ancora scritto in questo giro (vedi nota nel prossimo passo).
"""
from decimal import Decimal

from src.tpo_core.diario_web.rendiconto import (
    RigaConsegnaOggi,
    RigaDaChiarire,
    RendicontoDelGiorno,
    _risolvi_consegne,
)


def _riga(ordine="ORD-000001", cliente="Abaluus", varieta="Afila",
          quantita="2", unita="SET"):
    return (ordine, cliente, varieta, Decimal(quantita), unita)


def test_riga_coperta_da_stock_sufficiente_finisce_in_consegne():
    consegne, da_chiarire = _risolvi_consegne(
        [_riga(quantita="2")],
        {("Afila", "SET"): Decimal("5")},
    )
    assert da_chiarire == []
    assert consegne == [
        RigaConsegnaOggi("ORD-000001", "Abaluus", "Afila", Decimal("2"), "SET", Decimal("5"))
    ]


def test_riga_senza_nessuno_stock_finisce_in_da_chiarire():
    consegne, da_chiarire = _risolvi_consegne([_riga()], {})
    assert consegne == []
    assert len(da_chiarire) == 1
    assert da_chiarire[0].motivo == "nessuno stock vivo in SET per Afila"


def test_riga_con_stock_insufficiente_finisce_in_da_chiarire():
    consegne, da_chiarire = _risolvi_consegne(
        [_riga(quantita="3")],
        {("Afila", "SET"): Decimal("1")},
    )
    assert consegne == []
    assert len(da_chiarire) == 1
    assert "insufficiente" in da_chiarire[0].motivo
    assert da_chiarire[0].quantita_richiesta == Decimal("3")


def test_stock_in_unita_diversa_non_copre_la_riga():
    """Stesso principio del delivery_fulfilment_writer reale (Fatto 22): lo
    stock deve combaciare per unita' di misura, non solo per varieta'."""
    consegne, da_chiarire = _risolvi_consegne(
        [_riga(quantita="2", unita="SET")],
        {("Afila", "GRAM"): Decimal("9999")},
    )
    assert consegne == []
    assert da_chiarire[0].motivo == "nessuno stock vivo in SET per Afila"


def test_righe_multiple_si_smistano_indipendentemente():
    righe = [
        _riga(ordine="ORD-000001", cliente="Abaluus", varieta="Afila", quantita="2"),
        _riga(ordine="ORD-000002", cliente="Selvaje", varieta="Cilantro", quantita="1"),
    ]
    stock = {("Afila", "SET"): Decimal("5")}
    consegne, da_chiarire = _risolvi_consegne(righe, stock)
    assert len(consegne) == 1
    assert consegne[0].varieta_denominazione == "Afila"
    assert len(da_chiarire) == 1
    assert da_chiarire[0].varieta_denominazione == "Cilantro"


def test_rendiconto_vuoto_quando_nessuna_riga():
    r = RendicontoDelGiorno(data="2026-09-30", da_chiarire=(), consegne=(), da_seminare=())
    assert r.vuoto is True


def test_rendiconto_non_vuoto_se_solo_da_chiarire():
    r = RendicontoDelGiorno(
        data="2026-09-30",
        da_chiarire=(RigaDaChiarire("ORD-1", "X", "Y", Decimal("1"), "SET", "motivo"),),
        consegne=(), da_seminare=(),
    )
    assert r.vuoto is False
