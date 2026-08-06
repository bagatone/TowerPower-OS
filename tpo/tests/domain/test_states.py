from src.tpo_core.domain.states import (
    ConsegnaState,
    MovimentoDirection,
    MovimentoType,
    OrdineCreationType,
    OrdineState,
    ProgrammaFornituraState,
    RunState,
    SeminaState,
    VarietaState,
)


def values(enum_type) -> list[str]:
    return [item.value for item in enum_type]


def test_varieta_states_are_exact() -> None:
    assert values(VarietaState) == ["ATTIVA", "IN_SPERIMENTAZIONE", "SOSPESA", "DISMESSA"]


def test_semina_states_are_exact() -> None:
    assert values(SeminaState) == [
        "AVVIATA",
        "GERMINAZIONE",
        "LUCE",
        "CRESCITA",
        "PRONTA_ALLA_RACCOLTA",
        "CHIUSA",
    ]


def test_programma_fornitura_states_are_exact() -> None:
    assert values(ProgrammaFornituraState) == ["ATTIVO", "SOSPESO", "TERMINATO"]


def test_ordine_states_are_exact() -> None:
    assert values(OrdineState) == ["APERTO", "PARZIALMENTE_EVASO", "EVASO", "ANNULLATO"]


def test_ordine_creation_types_are_exact() -> None:
    assert values(OrdineCreationType) == ["AUTOMATICO", "MANUALE"]


def test_consegna_states_are_exact() -> None:
    assert values(ConsegnaState) == [
        "PROGRAMMATA",
        "IN_PREPARAZIONE",
        "CONSEGNATA",
        "ANNULLATA",
    ]


def test_movimento_types_are_exact() -> None:
    assert values(MovimentoType) == ["CARICO", "SCARICO", "RETTIFICA"]


def test_movimento_directions_are_exact() -> None:
    assert values(MovimentoDirection) == ["POSITIVO", "NEGATIVO"]


def test_run_states_are_exact() -> None:
    assert values(RunState) == ["SUCCESS", "SUCCESS_WITH_WARNINGS", "FAILED"]
