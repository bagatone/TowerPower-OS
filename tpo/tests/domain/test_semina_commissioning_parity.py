from datetime import datetime, timezone
from decimal import Decimal
import pytest

from src.tpo_core.domain.entities.semina import Semina
from src.tpo_core.domain.errors import InvariantViolationError
from src.tpo_core.domain.identifiers import LottoSemeId, ProtocolloVersioneId, SeminaId, VarietaId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import SeminaState


def _semina(**changes):
    values = dict(id=SeminaId("SEM-000001"), varieta_id=VarietaId("VAR-000001"),
                  stato=SeminaState.AVVIATA, quantita_seme=Quantity(Decimal("1"), UnitOfMeasure.GRAM),
                  data_avvio=datetime(2026, 8, 25, tzinfo=timezone.utc), cultivar="Afila",
                  uso_produttivo="Microgreen", lotto_seme="LSE-000001",
                  versione_protocollo="PV-000001", causa_origine="ORDINE_CLIENTE",
                  lotto_seme_id=LottoSemeId("LSE-000001"),
                  protocollo_versione_id=ProtocolloVersioneId("PV-000001"))
    return Semina(**(values | changes))


def test_typed_context_and_predictive_quartet_null():
    semina = _semina()
    assert semina.lotto_seme_id == LottoSemeId("LSE-000001")
    assert semina.protocollo_versione_id == ProtocolloVersioneId("PV-000001")
    assert (semina.expected_useful_quantity, semina.expected_useful_uom,
            semina.harvest_window_start, semina.harvest_window_end) == (None, None, None, None)


def test_partial_predictive_authority_is_rejected():
    with pytest.raises(InvariantViolationError):
        _semina(expected_useful_quantity=Quantity(Decimal("1"), UnitOfMeasure.SET))


@pytest.mark.parametrize("field,value", [
    ("lotto_seme_id", None), ("lotto_seme_id", "LSE-000001"),
    ("protocollo_versione_id", None), ("protocollo_versione_id", "PV-000001"),
])
def test_constitutive_public_references_are_required_and_typed(field, value):
    with pytest.raises(InvariantViolationError):
        _semina(**{field: value})


def test_populated_prediction_matches_persistence_constraints():
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    end = datetime(2026, 9, 2, tzinfo=timezone.utc)
    valid = _semina(
        expected_useful_quantity=Quantity(Decimal("1"), UnitOfMeasure.SET),
        expected_useful_uom=UnitOfMeasure.SET,
        harvest_window_start=start, harvest_window_end=end,
    )
    assert valid.harvest_window_end > valid.harvest_window_start
    for changes in (
        {"expected_useful_quantity": Quantity(Decimal("0"), UnitOfMeasure.SET)},
        {"expected_useful_quantity": "1"},
        {"expected_useful_uom": "SET"},
        {"harvest_window_end": start},
    ):
        with pytest.raises(InvariantViolationError):
            _semina(**({
                "expected_useful_quantity": Quantity(Decimal("1"), UnitOfMeasure.SET),
                "expected_useful_uom": UnitOfMeasure.SET,
                "harvest_window_start": start, "harvest_window_end": end,
            } | changes))
