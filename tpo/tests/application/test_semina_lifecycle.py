from datetime import datetime, timezone

import pytest

from src.tpo_core.application.semina_commissioning.models import SeminaFactSource
from src.tpo_core.application.semina_lifecycle import (
    ALLOWED_EDGES, SeminaFinalOutcome, SeminaLifecycleAuthority,
    TransitionSemina, validate_transition,
)
from src.tpo_core.application.semina_lifecycle.errors import (
    SeminaFinalOutcomeForbiddenError, SeminaFinalOutcomeRequiredError,
    SeminaLifecycleProvenanceInvalidError, SeminaLifecycleTimestampInvalidError,
    SeminaTransitionInvalidError,
)
from src.tpo_core.domain.identifiers import ActorId, SeminaId
from src.tpo_core.domain.states import SeminaState
from src.tpo_core.infrastructure.postgresql.semina_lifecycle import (
    DOMAIN_TO_POSTGRESQL_OUTCOME, POSTGRESQL_TO_DOMAIN_OUTCOME,
    outcome_from_postgresql, outcome_to_postgresql,
)
from src.tpo_core.application.semina_lifecycle.errors import SeminaLifecycleReconciliationRequiredError


NOW = datetime(2026, 8, 25, 9, tzinfo=timezone.utc)


def command(**overrides):
    target = overrides.get("target_state", SeminaState.GERMINAZIONE)
    facts = {"target_state", "effective_at"}
    if target is SeminaState.CHIUSA:
        facts.add("final_outcome")
    values = dict(
        semina_public_id=SeminaId("SEM-000001"), expected_semina_version=0,
        target_state=target, effective_at=NOW,
        final_outcome=(SeminaFinalOutcome.INTERRUZIONE
                       if target is SeminaState.CHIUSA else None),
        provenance=tuple((f, SeminaFactSource.OWNER_AUTHORIZED) for f in facts),
        authority=SeminaLifecycleAuthority(ActorId("owner"), "physical transition", "corr", "idem"),
    )
    values.update(overrides)
    return TransitionSemina(**values)


def test_exact_frozen_graph():
    expected = {
        (SeminaState.AVVIATA, SeminaState.GERMINAZIONE),
        (SeminaState.GERMINAZIONE, SeminaState.LUCE),
        (SeminaState.LUCE, SeminaState.CRESCITA),
        (SeminaState.CRESCITA, SeminaState.PRONTA_ALLA_RACCOLTA),
        *((state, SeminaState.CHIUSA) for state in SeminaState if state is not SeminaState.CHIUSA),
    }
    assert ALLOWED_EDGES == frozenset(expected)
    for edge in expected:
        validate_transition(*edge)
    for source in SeminaState:
        for target in SeminaState:
            if (source, target) not in expected:
                with pytest.raises(SeminaTransitionInvalidError):
                    validate_transition(source, target)


def test_closure_outcome_required_and_active_forbids_it():
    with pytest.raises(SeminaFinalOutcomeRequiredError):
        command(target_state=SeminaState.CHIUSA, final_outcome=None,
                provenance=(("target_state", SeminaFactSource.OWNER_AUTHORIZED),
                            ("effective_at", SeminaFactSource.OWNER_AUTHORIZED),
                            ("final_outcome", SeminaFactSource.OWNER_AUTHORIZED)))
    with pytest.raises(SeminaFinalOutcomeForbiddenError):
        command(final_outcome=SeminaFinalOutcome.INTERRUZIONE)


def test_timestamp_and_provenance_fail_closed():
    with pytest.raises(SeminaLifecycleTimestampInvalidError):
        command(effective_at=datetime(2026, 8, 25, 9))
    with pytest.raises(SeminaLifecycleProvenanceInvalidError):
        command(provenance=(("target_state", SeminaFactSource.OWNER_AUTHORIZED),))


def test_payload_is_stable_and_excludes_execution_context():
    first = command()
    second = command(authority=SeminaLifecycleAuthority(
        ActorId("other"), "other reason", "other-corr", "other-key"))
    assert first.canonical_payload_hash == second.canonical_payload_hash
    assert len(first.canonical_payload_hash) == 64


def test_domain_postgresql_outcome_mapping_is_explicit_total_and_roundtrips():
    assert set(DOMAIN_TO_POSTGRESQL_OUTCOME) == set(SeminaFinalOutcome)
    assert set(POSTGRESQL_TO_DOMAIN_OUTCOME.values()) == set(SeminaFinalOutcome)
    assert set(POSTGRESQL_TO_DOMAIN_OUTCOME) == {
        "RACCOLTA_COMPLETA", "RACCOLTA_PARZIALE_CON_SCARTO",
        "SCARTO_TOTALE", "INTERRUZIONE",
    }
    for outcome in SeminaFinalOutcome:
        assert outcome_from_postgresql(outcome_to_postgresql(outcome)) is outcome
    assert outcome_to_postgresql(None) is None
    assert outcome_from_postgresql(None) is None


def test_unmapped_outcomes_fail_closed():
    with pytest.raises(SeminaLifecycleReconciliationRequiredError):
        outcome_to_postgresql("SCARTO_TOTALE")  # type: ignore[arg-type]
    with pytest.raises(SeminaLifecycleReconciliationRequiredError):
        outcome_from_postgresql("UNKNOWN")
