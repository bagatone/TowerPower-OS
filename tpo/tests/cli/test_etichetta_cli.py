from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.bolla_lettura.models import Bolla, OrigineLotto, RigaBolla
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.etichetta import _EtichetteError, costruisci_etichette
from src.tpo_core.domain.identifiers import ConsegnaId
from src.tpo_core.infrastructure.pdf.etichette_pdf import Etichetta, render_etichette_pdf


def riga(nome, qty, codice, senza="0", uom="SET"):
    origini = (OrigineLotto(codice, "RAC-000001", datetime(2026, 10, 3, 6, 30, tzinfo=timezone.utc), Decimal(qty)),)
    return RigaBolla(1, "ORD-000001", "VAR-000001", nome, Decimal(qty) + Decimal(senza), uom, False,
                     origini, Decimal(senza))


def bolla(*righe):
    return Bolla(ConsegnaId("CON-000004"), "CONSEGNATA", "CLI-000011", "Hotel Secret Bahia Real",
                 date(2026, 10, 5), datetime(2026, 10, 5, 9, 13, tzinfo=timezone.utc), None, None, tuple(righe))


def test_one_label_per_set_per_variety():
    etichette, senza = costruisci_etichette(
        bolla(riga("Afila", "1", "AFI-1409-A"), riga("Rábano", "1", "RAB-2609-A"), riga("Mizuna", "1", "MIZ-1609-A")))
    assert len(etichette) == 3 and senza == []
    assert [e.varieta for e in etichette] == ["Afila", "Rábano", "Mizuna"]


def test_two_sets_two_labels_and_half_set_gets_one_label():
    assert len(costruisci_etichette(bolla(riga("Afila", "2", "AFI-1409-A")))[0]) == 2
    etichette, _ = costruisci_etichette(bolla(riga("Cilantro", "0.5", "CIL-1709-A")))
    assert len(etichette) == 1


def test_labels_per_set_option_multiplies():
    assert len(costruisci_etichette(bolla(riga("Afila", "1", "AFI-1409-A")), 4)[0]) == 4


def test_quantity_without_origin_gets_no_label_and_is_reported():
    etichette, senza = costruisci_etichette(bolla(riga("Afila", "1", "AFI-1409-A", senza="1")))
    assert len(etichette) == 1 and senza == ["Afila 1 SET"]


def test_non_set_unit_is_rejected():
    with pytest.raises(_EtichetteError):
        costruisci_etichette(bolla(riga("Afila", "100", "AFI-1409-A", uom="GRAM")))


def test_pdf_has_one_page_per_label_at_62x29mm():
    data = render_etichette_pdf([Etichetta("Rábano", "RAB-2609-A", date(2026, 10, 3), "CON-000004")] * 3)
    assert data.startswith(b"%PDF") and data.count(b"/Type /Page\n") + data.count(b"/Type /Page ") >= 3
    assert b"175.748" in data  # 62 mm in punti
    with pytest.raises(ValueError):
        render_etichette_pdf([])


def test_parser_defaults():
    ns = main_module._parser().parse_args(["etichetta", "genera", "--consegna", "CON-000004"])
    assert ns.etichette_per_set == 1 and ns.etichetta_command == "genera"


def test_foglio_a4_puts_all_labels_on_one_page_and_paginates_after_27():
    from src.tpo_core.infrastructure.pdf.etichette_pdf import ETICHETTE_PER_FOGLIO, render_etichette_foglio_pdf
    e = Etichetta("Rábano", "RAB-2609-A", date(2026, 10, 3), "CON-000004")
    pagine = lambda d: d.count(b"/Type /Page\n") + d.count(b"/Type /Page ") + d.count(b"/Type /Page/")
    uno = render_etichette_foglio_pdf([e] * 3)
    assert uno.startswith(b"%PDF") and ETICHETTE_PER_FOGLIO == 27 and pagine(uno) == 1
    assert pagine(render_etichette_foglio_pdf([e] * 27)) == 1
    assert pagine(render_etichette_foglio_pdf([e] * 28)) == 2
    with pytest.raises(ValueError):
        render_etichette_foglio_pdf([])


def test_parser_accepts_foglio_flag():
    ns = main_module._parser().parse_args(["etichetta", "genera", "--consegna", "CON-000004", "--foglio"])
    assert ns.foglio is True
