from dataclasses import FrozenInstanceError

import pytest

from src.tpo_core.application.scheduling.provenance import OrderLineProvenance
from src.tpo_core.application.scheduling.provenance import (
    VersionedProgramLine,
    VersionedProgrammaFornitura,
)
from src.tpo_core.domain.entities.programma_fornitura import (
    ConfigurazioneTemporale,
    ProgrammaFornitura,
    RigaProgrammaFornitura,
    TipoRicorrenza,
)
from src.tpo_core.domain.identifiers import ClienteId, VarietaId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import ProgrammaFornituraState
from datetime import date
from src.tpo_core.domain.errors import InvariantViolationError
from src.tpo_core.domain.identifiers import ProgrammaFornituraId


def provenance(**overrides):
    values = {
        "programma_fornitura_id": ProgrammaFornituraId("PF-000001"),
        "programma_version": 1,
        "programma_line_position": 2,
        "order_line_position": 1,
    }
    values.update(overrides)
    return OrderLineProvenance(**values)


def test_modello_provider_neutral_valido_e_immutabile():
    item = provenance()
    assert item.programma_version == 1
    with pytest.raises(FrozenInstanceError):
        item.order_line_position = 2


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("programma_version", 0),
        ("programma_line_position", 0),
        ("order_line_position", 0),
        ("order_line_position", True),
    ),
)
def test_posizioni_e_versione_devono_essere_positive(name, value):
    with pytest.raises(InvariantViolationError):
        provenance(**{name: value})


def test_programma_id_obbligatorio_e_tipizzato():
    with pytest.raises(InvariantViolationError):
        provenance(programma_fornitura_id="PF-000001")


def test_modulo_non_dipende_da_infrastructure():
    import inspect
    import src.tpo_core.application.scheduling.provenance as module

    assert "infrastructure" not in inspect.getsource(module)


def test_wrapper_versionato_richiede_versione_e_posizioni_autorevoli():
    line = RigaProgrammaFornitura(
        VarietaId("VAR-000001"),
        Quantity(2, UnitOfMeasure.SET),
        ConfigurazioneTemporale(TipoRicorrenza.SETTIMANALE),
    )
    programma = ProgrammaFornitura(
        ProgrammaFornituraId("PF-000001"), ClienteId("CLI-000001"), (line,),
        date(2026, 8, 3), ProgrammaFornituraState.ATTIVO, 0,
    )
    wrapped = VersionedProgrammaFornitura(
        programma, 3, (VersionedProgramLine(7, line),)
    )
    assert wrapped.version == 3
    assert wrapped.lines[0].position == 7
    with pytest.raises(InvariantViolationError):
        VersionedProgrammaFornitura(programma, 0, wrapped.lines)
