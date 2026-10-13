from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.bolla_lettura import (
    Bolla, BollaLetturaService, ConsegnaNonConsegnataError,
    InvalidBollaLetturaQueryError, OrigineLotto, RichiediBolla, RigaBolla,
)
from src.tpo_core.domain.identifiers import ConsegnaId

NOW = datetime(2099, 1, 1, 10, tzinfo=timezone.utc)


def _bolla(stato: str = "CONSEGNATA", righe=None) -> Bolla:
    return Bolla(
        ConsegnaId("CON-000001"), stato, "CLI-000001", "Cliente Prova", date(2099, 1, 1),
        NOW if stato == "CONSEGNATA" else None, "Matteo", None,
        righe if righe is not None else (
            RigaBolla(
                1, "ORD-000001", "VAR-000001", "Rábano", Decimal("3"), "SET", False,
                (OrigineLotto("RAB-0210-A", "RAC-000001", NOW, Decimal("2")),),
                Decimal("1"),
            ),
            RigaBolla(2, "ORD-000001", "VAR-000003", "Cilantro", Decimal("1"), "SET",
                      False, (), Decimal("1")),
        ),
    )


class _Reader:
    def __init__(self, bolla: Bolla) -> None:
        self._bolla = bolla

    def bolla(self, query: RichiediBolla) -> Bolla:
        return self._bolla


def test_service_returns_bolla_for_consegnata() -> None:
    result = BollaLetturaService(_Reader(_bolla())).bolla(RichiediBolla(ConsegnaId("CON-000001")))
    assert result.consegna_id.value == "CON-000001"
    assert result.righe_senza_origine == 2


def test_service_refuses_consegna_not_yet_delivered() -> None:
    service = BollaLetturaService(_Reader(_bolla("PROGRAMMATA")))
    with pytest.raises(ConsegnaNonConsegnataError):
        service.bolla(RichiediBolla(ConsegnaId("CON-000001")))


def test_service_rejects_invalid_query() -> None:
    with pytest.raises(InvalidBollaLetturaQueryError):
        BollaLetturaService(_Reader(_bolla())).bolla("CON-000001")  # type: ignore[arg-type]
    with pytest.raises(InvalidBollaLetturaQueryError):
        RichiediBolla("CON-000001")  # type: ignore[arg-type]


def test_render_pdf_contains_codes_and_untraced_notice() -> None:
    pytest.importorskip("reportlab")
    from src.tpo_core.infrastructure.pdf.bolla_pdf import format_quantity, render_bolla_pdf

    assert format_quantity(Decimal("3.000000")) == "3"
    assert format_quantity(Decimal("1.500000")) == "1,5"
    assert format_quantity(Decimal("0.250000")) == "0,25"
    assert format_quantity(Decimal("10")) == "10"

    pdf = render_bolla_pdf(
        _bolla(), emittente=["Tower Power (prova)"], generata_il=NOW, compress=False,
    )
    assert pdf.startswith(b"%PDF-")
    assert b"(CON-000001" in pdf
    assert b"RAB-0210-A" in pdf
    assert b"RAC-000001" in pdf
    assert b"ALBAR" in pdf
    assert b"Origen no trazado" in pdf


def _con_pagamento(**kwargs):
    from dataclasses import replace
    from src.tpo_core.application.bolla_lettura import PagamentoBolla
    return replace(_bolla(), pagamento=PagamentoBolla(**kwargs))


def test_pdf_payment_status_line_unpaid_paid_and_historical() -> None:
    pytest.importorskip("reportlab")
    from src.tpo_core.infrastructure.pdf.bolla_pdf import estado_pagamento, render_bolla_pdf

    assert estado_pagamento(_bolla()) == "PENDIENTE DE PAGO"
    pagata = _con_pagamento(pagamento_id="PGC-000001", data_pagamento=date(2026, 10, 9),
                            metodo="BIZUM", importo=Decimal("12.50"), storico=False)
    assert estado_pagamento(pagata.pagamento and pagata) == "PAGADO el 09/10/2026 - Bizum - 12,5 EUR"
    senza_importo = _con_pagamento(pagamento_id="PGC-000001", data_pagamento=date(2026, 10, 9),
                                   metodo="CONTANTI", importo=None, storico=False)
    assert estado_pagamento(senza_importo) == "PAGADO el 09/10/2026 - efectivo"
    storica = _con_pagamento(pagamento_id="PGC-000001", data_pagamento=date(2026, 10, 11),
                             metodo="ALTRO", importo=None, storico=True)
    text = estado_pagamento(storica)
    assert "registrado el 11/10/2026" in text and "anterior al control de pagos" in text
    assert "otro" not in text            # il metodo segnaposto non compare mai sulla bolla

    for bolla, atteso in ((_bolla(), b"PENDIENTE DE PAGO"), (pagata, b"PAGADO el 09/10/2026")):
        pdf = render_bolla_pdf(bolla, emittente=["Tower Power (prova)"], generata_il=NOW,
                               compress=False)
        assert atteso in pdf
