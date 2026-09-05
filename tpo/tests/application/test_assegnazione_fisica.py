from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.assegnazione_fisica.errors import (
    InvalidAssegnazioneFisicaCommandError,
)
from src.tpo_core.application.assegnazione_fisica.models import (
    AssegnazioneFisicaAuthority, RegistraAssegnazioneFisica,
)
from src.tpo_core.application.assegnazione_fisica.service import AssegnazioneFisicaService
from src.tpo_core.domain.identifiers import ActorId, ConsegnaId, RaccoltaId, RigaOrdineId


AUTH = AssegnazioneFisicaAuthority(ActorId("operatore"), "assegnazione fisica", "corr", "idem")


def command(**changes):
    values = dict(
        raccolta_id=RaccoltaId("RAC-000001"),
        riga_ordine_id=RigaOrdineId("RO-000001"),
        quantita_assegnata=Decimal("120.5"),
        unita_misura="GRAM",
        effective_at=datetime(2026, 9, 5, 8, tzinfo=timezone.utc),
        motivo="assegnazione raccolta a riga ordine",
        authority=AUTH,
    )
    values.update(changes)
    return RegistraAssegnazioneFisica(**values)


def test_canonical_payload_is_deterministic_and_64_hex():
    value = command()
    assert len(value.canonical_payload_hash) == 64
    assert value.canonical_payload_hash == command().canonical_payload_hash
    assert value.effective_at.tzinfo is timezone.utc


def test_canonical_payload_is_sensitive_to_quantity_raccolta_riga_ordine_and_consegna():
    base = command()
    different_quantity = command(quantita_assegnata=Decimal("120.6"))
    different_raccolta = command(raccolta_id=RaccoltaId("RAC-000002"))
    different_riga_ordine = command(riga_ordine_id=RigaOrdineId("RO-000002"))
    with_consegna = command(consegna_id=ConsegnaId("CON-000001"))
    assert base.canonical_payload_hash != different_quantity.canonical_payload_hash
    assert base.canonical_payload_hash != different_raccolta.canonical_payload_hash
    assert base.canonical_payload_hash != different_riga_ordine.canonical_payload_hash
    assert base.canonical_payload_hash != with_consegna.canonical_payload_hash


def test_consegna_id_defaults_to_none():
    assert command().consegna_id is None


def test_consegna_id_accepts_typed_identifier():
    value = command(consegna_id=ConsegnaId("CON-000001"))
    assert value.consegna_id == ConsegnaId("CON-000001")


def test_wrong_consegna_id_type_is_rejected():
    with pytest.raises(InvalidAssegnazioneFisicaCommandError):
        command(consegna_id="CON-000001")


@pytest.mark.parametrize("value", ["0", "-1", "1.0000001"])
def test_nonpositive_or_overprecision_quantity_is_rejected(value):
    with pytest.raises(InvalidAssegnazioneFisicaCommandError):
        command(quantita_assegnata=Decimal(value))


def test_invalid_unita_misura_is_rejected():
    with pytest.raises(InvalidAssegnazioneFisicaCommandError):
        command(unita_misura="KG")


def test_naive_effective_at_is_rejected():
    with pytest.raises(InvalidAssegnazioneFisicaCommandError):
        command(effective_at=datetime(2026, 9, 5, 8))


def test_blank_motivo_is_rejected():
    with pytest.raises(InvalidAssegnazioneFisicaCommandError):
        command(motivo="   ")


def test_wrong_raccolta_id_type_is_rejected():
    with pytest.raises(InvalidAssegnazioneFisicaCommandError):
        command(raccolta_id="RAC-000001")


def test_wrong_riga_ordine_id_type_is_rejected():
    with pytest.raises(InvalidAssegnazioneFisicaCommandError):
        command(riga_ordine_id="RO-000001")


def test_service_is_thin_and_typed():
    class Writer:
        def registra(self, value):
            assert value == command()
            return "ok"

    service = AssegnazioneFisicaService(Writer())
    assert service.registra(command()) == "ok"
    with pytest.raises(InvalidAssegnazioneFisicaCommandError):
        service.registra(object())
