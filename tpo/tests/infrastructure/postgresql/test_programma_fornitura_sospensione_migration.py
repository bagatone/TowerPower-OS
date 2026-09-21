from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).parents[3]
SOURCE_PATH = ROOT / "migrations/versions/20260916_0034_programma_fornitura_sospensione.py"


def test_programma_fornitura_sospensione_migration_is_linear_head():
    config = Config(str(ROOT / "migrations/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["20260919_0035"]
    revision = script.get_revision("20260916_0034")
    assert revision.down_revision == "20260915_0033"


def test_programma_fornitura_sospensione_migration_uses_established_offline_mode_precedent():
    source = SOURCE_PATH.read_text()
    assert "from alembic import context, op" in source
    assert "context.is_offline_mode()" in source
    assert "bind.dialect.name != \"postgresql\"" in source
    assert "op.get_context().as_sql" not in source


def test_programma_fornitura_sospensione_migration_adds_header_column():
    source = SOURCE_PATH.read_text()
    for fragment in (
        'op.add_column(\n        "programmi_fornitura", sa.Column("data_ripresa_prevista", sa.Date())',
        'op.drop_column("programmi_fornitura", "data_ripresa_prevista", schema=SCHEMA)',
    ):
        assert fragment in source


def test_programma_fornitura_sospensione_migration_creates_both_reservation_tables():
    source = SOURCE_PATH.read_text()
    for fragment in (
        "programma_fornitura_sospendi_requests",
        "programma_fornitura_riattiva_requests",
        "PROGRAMMA_FORNITURA_SOSPENDI_V1",
        "PROGRAMMA_FORNITURA_RIATTIVA_V1",
        "result_data_ripresa_prevista",
        "fk_pf_sospendi_result_versione",
        "fk_pf_riattiva_result_versione",
        "uq_pf_sospendi_request_key",
        "uq_pf_riattiva_request_key",
    ):
        assert fragment in source


def test_programma_fornitura_sospensione_migration_does_not_add_a_unique_constraint_on_programma_alone():
    # Design deliberato (vedi docstring della migrazione): a differenza di
    # RACCOLTA, lo stesso PROGRAMMA_FORNITURA puo' essere sospeso e
    # riattivato piu' volte, quindi l'unicita' e' solo su
    # (operation_scope,idempotency_key), mai su programma_fornitura_id da solo.
    source = SOURCE_PATH.read_text()
    assert 'sa.UniqueConstraint("operation_scope", "idempotency_key", name=unique_name)' in source
    assert "programma_fornitura_id\", unique=True" not in source


def test_programma_fornitura_sospensione_migration_downgrade_guards_existing_rows():
    source = SOURCE_PATH.read_text()
    assert "cannot downgrade: governed" in source
    assert "authority history exists" in source


def test_programma_fornitura_sospensione_migration_has_no_business_dml():
    source = SOURCE_PATH.read_text()
    for statement in ("INSERT INTO", "UPDATE tpo.", "DELETE FROM"):
        assert statement not in source
    assert "id_sequences" not in source
