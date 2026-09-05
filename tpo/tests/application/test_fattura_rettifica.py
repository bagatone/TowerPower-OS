from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.fattura_rettifica.errors import InvalidRectifyFatturaCommandError
from src.tpo_core.application.fattura_rettifica.models import (
    RectifyFattura, RectifyFatturaAuthority, RectifyFatturaResult, RettificaRigaFattura,
)
from src.tpo_core.application.fattura_rettifica.service import FatturaRettificaService
from src.tpo_core.domain.identifiers import ActorId, ClienteId, NumeroFattura


def authority(**changes):
    values = dict(actor=ActorId("owner"), reason="rettifica", correlation_id="corr-1",
                  idempotency_key="key-1")
    values.update(changes)
    return RectifyFatturaAuthority(**values)


def riga(**changes):
    values = dict(posizione_originale=1, quantita=Decimal("-1"))
    values.update(changes)
    return RettificaRigaFattura(**values)


def command(**changes):
    values = dict(
        rettifica_di=NumeroFattura("2026/0001"),
        righe=(riga(),),
        data_emissione=date(2026, 9, 5),
        authority=authority(),
    )
    values.update(changes)
    return RectifyFattura(**values)


def test_canonical_payload_hash_is_stable_and_deterministic():
    first = command()
    assert first.canonical_payload_hash == command().canonical_payload_hash
    assert len(first.canonical_payload_hash) == 64
    assert "2026/0001" in first.canonical_payload


def test_canonical_payload_is_order_independent_but_content_sensitive():
    two_righe = command(righe=(riga(posizione_originale=1, quantita=Decimal("-1")),
                                riga(posizione_originale=2, quantita=Decimal("-2"))))
    reordered = command(righe=(riga(posizione_originale=2, quantita=Decimal("-2")),
                                riga(posizione_originale=1, quantita=Decimal("-1"))))
    assert two_righe.canonical_payload_hash == reordered.canonical_payload_hash


def test_payload_excludes_runtime_authority_but_includes_business_facts():
    first = command()
    second = command(authority=authority(actor=ActorId("other"), correlation_id="corr-2",
                                          idempotency_key="key-2"))
    assert first.canonical_payload_hash == second.canonical_payload_hash
    assert first.canonical_payload_hash != command(
        rettifica_di=NumeroFattura("2026/0002")
    ).canonical_payload_hash
    assert first.canonical_payload_hash != command(
        data_emissione=date(2026, 9, 6)
    ).canonical_payload_hash
    assert first.canonical_payload_hash != command(
        righe=(riga(quantita=Decimal("-2")),)
    ).canonical_payload_hash


def test_rejects_empty_or_duplicate_posizione_righe():
    with pytest.raises(InvalidRectifyFatturaCommandError):
        command(righe=())
    with pytest.raises(InvalidRectifyFatturaCommandError):
        command(righe=(riga(posizione_originale=1), riga(posizione_originale=1)))


def test_rejects_zero_or_non_decimal_quantita():
    with pytest.raises(InvalidRectifyFatturaCommandError):
        riga(quantita=Decimal("0"))
    with pytest.raises(InvalidRectifyFatturaCommandError):
        riga(quantita=1)


def test_rejects_non_positive_posizione_originale():
    with pytest.raises(InvalidRectifyFatturaCommandError):
        riga(posizione_originale=0)
    with pytest.raises(InvalidRectifyFatturaCommandError):
        riga(posizione_originale=-1)


def test_rejects_invalid_authority_fields():
    with pytest.raises(InvalidRectifyFatturaCommandError):
        authority(reason="  ")
    with pytest.raises(InvalidRectifyFatturaCommandError):
        authority(idempotency_key="")


class Writer:
    def __init__(self):
        self.commands = []

    def rectify(self, item):
        self.commands.append(item)
        return RectifyFatturaResult(
            2, "INSERTED", NumeroFattura("2026/0002"), item.rettifica_di,
            ClienteId("CLI-000001"), item.data_emissione, date(2026, 10, 5),
            Decimal("-10.00"), Decimal("-0.70"), Decimal("-10.70"), 1,
            datetime.now(timezone.utc),
        )


def test_service_delegates_typed_command_only():
    item = command()
    writer = Writer()
    result = FatturaRettificaService(writer).rectify(item)
    assert result.fattura_id == 2
    assert result.numero_fattura == NumeroFattura("2026/0002")
    assert writer.commands == [item]
    with pytest.raises(InvalidRectifyFatturaCommandError):
        FatturaRettificaService(writer).rectify(object())
