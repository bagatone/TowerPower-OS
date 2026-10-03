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
    assert b"Origine non tracciata" in pdf
