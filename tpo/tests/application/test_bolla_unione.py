"""Unione di due bolle dello stesso cliente (16/10/2026, Puipana CON-000020 + CON-000024). Nessun database."""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.tpo_core.application.bolla_lettura import (
    Bolla, PagamentoBolla, RigaBolla, UnioneBolleError, unisci_bolle,
)
from src.tpo_core.domain.identifiers import ConsegnaId

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "commissioning" / "2026-10-16_unisci_bolle.py"
GIORNO15 = datetime(2026, 10, 15, 11, tzinfo=timezone.utc)
GIORNO16 = datetime(2026, 10, 16, 10, tzinfo=timezone.utc)


def _riga(pos, varieta, qta) -> RigaBolla:
    return RigaBolla(pos, "ORD-000001", "VAR-000001", varieta, Decimal(qta), "SET", False, (), Decimal(qta))


def _bolla(codice, quando, righe, cliente="CLI-000009", pagamento=None, stato="CONSEGNATA") -> Bolla:
    return Bolla(ConsegnaId(codice), stato, cliente, "Puipana", quando.date(), quando, "Matteo", None,
                 tuple(righe), pagamento)


def _coppia():
    # passate in ordine rovesciato di proposito: l'unione le mette in ordine di giorno
    vecchia = _bolla("CON-000020", GIORNO15, [_riga(1, "Afila", "0.5"), _riga(2, "Cilantro", "0.5")])
    nuova = _bolla("CON-000024", GIORNO16, [_riga(1, "Rábano", "0.5")])
    return nuova, vecchia


def test_unisce_in_ordine_di_giorno_senza_cambiare_quantita() -> None:
    unita = unisci_bolle(_coppia())
    assert unita.consegne_unite == ("CON-000020", "CON-000024")
    assert unita.consegna_id.value == "CON-000024"
    assert [(r.posizione, r.varieta_denominazione, r.quantita, r.consegna_origine) for r in unita.righe] == [
        (1, "Afila", Decimal("0.5"), "CON-000020"), (2, "Cilantro", Decimal("0.5"), "CON-000020"),
        (3, "Rábano", Decimal("0.5"), "CON-000024")]
    assert unita.righe[0].data_consegna_origine == date(2026, 10, 15)
    assert unita.pagamento is None


@pytest.mark.parametrize("modifica,testo", [
    (lambda a, b: (a, replace(b, cliente_id="CLI-000010")), "clienti diversi"),
    (lambda a, b: (a, replace(b, stato="PROGRAMMATA")), "CONSEGNATE"),
    (lambda a, b: (a, a), "piu' volte"),
])
def test_rifiuta_se_non_unibili(modifica, testo) -> None:
    a, b = _coppia()
    with pytest.raises(UnioneBolleError, match=testo):
        unisci_bolle(modifica(a, b))
    with pytest.raises(UnioneBolleError, match="almeno due"):
        unisci_bolle([a])


def test_pagamenti_misti_rifiutati_e_uguali_uniti() -> None:
    a, b = _coppia()
    pag = lambda i, importo: PagamentoBolla(i, date(2026, 10, 16), "BIZUM", importo, False)  # noqa: E731
    with pytest.raises(UnioneBolleError, match="pagate e altre no"):
        unisci_bolle([replace(a, pagamento=pag("PGC-000001", None)), b])
    diverso = replace(b, pagamento=PagamentoBolla("PGC-000002", date(2026, 10, 17), "BIZUM", None, False))
    with pytest.raises(UnioneBolleError, match="date o con metodi diversi"):
        unisci_bolle([replace(a, pagamento=pag("PGC-000001", None)), diverso])
    unita = unisci_bolle([replace(a, pagamento=pag("PGC-000001", Decimal("5"))),
                          replace(b, pagamento=pag("PGC-000002", Decimal("7")))])
    assert unita.pagamento.importo == Decimal("12") and unita.pagamento.pagamento_id == "PGC-000002+PGC-000001"


def test_pdf_riporta_entrambe_le_consegne() -> None:
    pytest.importorskip("reportlab")
    from src.tpo_core.infrastructure.pdf.bolla_pdf import render_bolla_pdf
    pdf = render_bolla_pdf(unisci_bolle(_coppia()), emittente=["Tower Power (prova)"], generata_il=GIORNO16,
                           compress=False)
    for atteso in (b"CON-000020 + CON-000024", b"CON-000020 - 15/10/2026",
                   b"CON-000024 - 16/10/2026", b"15/10/2026 - 16/10/2026", b"PENDIENTE DE PAGO"):
        assert atteso in pdf


class _Service:
    def __init__(self, bolle) -> None:
        self.bolle = {b.consegna_id.value: b for b in bolle}

    def bolla(self, query):
        return self.bolle[query.consegna_id.value]


def _script():
    pytest.importorskip("reportlab")
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("unisci_bolle_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_script_anteprima_poi_esegui_sposta_i_singoli_e_rilancio_non_rifa(tmp_path) -> None:
    script = _script()
    a, b = _coppia()
    service = _Service([a, b])
    cliente = tmp_path / "puipana"
    cliente.mkdir()
    vecchi = [cliente / "bolla_CON-000020_puipana_2026-10-15.pdf", cliente / "bolla_CON-000024_puipana_2026-10-16.pdf"]
    for p in vecchi:
        p.write_bytes(b"%PDF-vecchio")
    altro = cliente / "bolla_CON-000099_puipana_2026-10-01.pdf"
    altro.write_bytes(b"%PDF-altro")
    righe: list[str] = []

    assert script.run(service, ["CON-000020", "CON-000024"], tmp_path, False, out=righe.append, ora=GIORNO16) == 0
    assert all(p.exists() for p in vecchi) and not (cliente / "unite").exists()
    assert not list(cliente.glob("bolla_CON-000020_CON-000024*"))

    righe.clear()
    assert script.run(service, ["CON-000020", "CON-000024"], tmp_path, True, out=righe.append, ora=GIORNO16) == 0
    unica = cliente / "bolla_CON-000020_CON-000024_puipana_2026-10-16.pdf"
    assert unica.read_bytes().startswith(b"%PDF-")
    assert [p.name for p in sorted((cliente / "unite").iterdir())] == [p.name for p in vecchi]
    assert altro.exists() and not any(p.exists() for p in vecchi)

    righe.clear()
    contenuto = unica.read_bytes()
    assert script.run(service, ["CON-000020", "CON-000024"], tmp_path, True, out=righe.append, ora=GIORNO16) == 0
    assert any("esiste gia'" in r for r in righe) and unica.read_bytes() == contenuto


def test_script_rifiuta_senza_scrivere(tmp_path) -> None:
    script = _script()
    a, b = _coppia()
    righe: list[str] = []
    assert script.run(_Service([a, replace(b, cliente_id="CLI-000010")]), ["CON-000020", "CON-000024"], tmp_path, True,
                      out=righe.append, ora=GIORNO16) == 2
    assert any("RIFIUTATO" in r for r in righe) and not list(tmp_path.iterdir())


def test_script_sovrascrivi_rifa_la_bolla_unica_e_rimpiazza_i_singoli_rigenerati(tmp_path) -> None:
    script = _script()
    a, b = _coppia()
    service = _Service([a, b])
    cliente = tmp_path / "puipana"
    (cliente / "unite").mkdir(parents=True)
    unica = cliente / "bolla_CON-000020_CON-000024_puipana_2026-10-16.pdf"
    unica.write_bytes(b"%PDF-vecchia-pendiente")
    vecchio = cliente / "unite" / "bolla_CON-000020_puipana_2026-10-15.pdf"
    vecchio.write_bytes(b"%PDF-vecchio")
    rigenerato = cliente / "bolla_CON-000020_puipana_2026-10-15.pdf"   # rigenerato dopo il pagamento
    rigenerato.write_bytes(b"%PDF-rigenerato")
    righe: list[str] = []

    script.run(service, ["CON-000020", "CON-000024"], tmp_path, True, out=righe.append, ora=GIORNO16)
    assert unica.read_bytes() == b"%PDF-vecchia-pendiente" and rigenerato.exists()   # senza flag non tocca nulla

    script.run(service, ["CON-000020", "CON-000024"], tmp_path, True, out=righe.append, ora=GIORNO16, sovrascrivi=True)
    assert unica.read_bytes().startswith(b"%PDF-1") and b"vecchia" not in unica.read_bytes()
    assert not rigenerato.exists() and vecchio.read_bytes() == b"%PDF-rigenerato"
