from alembic.script import ScriptDirectory

from src.tpo_core.infrastructure.postgresql.alembic import make_config


def test_lifecycle_migration_is_linear_current_head():
    script = ScriptDirectory.from_config(make_config())
    assert script.get_heads() == ["20260825_0020"]
    revision = script.get_revision("20260825_0020")
    assert revision.down_revision == "20260825_0019"


def test_lifecycle_migration_freezes_required_schema_and_protection():
    from pathlib import Path
    source = (Path(__file__).parents[3] / "migrations/versions/20260825_0020_semina_lifecycle_events.py").read_text()
    for token in (
        "semina_lifecycle_transition_requests", "semina_lifecycle_eventi",
        "effective_at", "recorded_at", "version_before", "version_after",
        "from_state", "to_state", "esito_finale", "provenance",
        "result_event_id", "fk_semina_lifecycle_request_authoritative_result",
        "uq_semina_lifecycle_event_id_request",
        "protect_semina_lifecycle_event", "protect_semina_lifecycle_request",
        "SEMINA_LIFECYCLE_TRANSITION_V1", "20260825_0019",
    ):
        assert token in source
    assert 'sa.Column("public_id"' not in source
    assert "id_sequences" not in source
