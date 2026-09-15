from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).parents[3]
SOURCE_PATH = ROOT / "migrations/versions/20260915_0033_raccolta_correzione_annotazione.py"


def test_raccolta_correzione_annotazione_migration_is_linear_head():
    config = Config(str(ROOT / "migrations/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["20260915_0033"]
    revision = script.get_revision("20260915_0033")
    assert revision.down_revision == "20260905_0032"


def test_raccolta_correzione_annotazione_migration_uses_established_offline_mode_precedent():
    source = SOURCE_PATH.read_text()
    assert "from alembic import context, op" in source
    assert "context.is_offline_mode()" in source
    assert "op.get_context().as_sql" not in source


def test_raccolta_correzione_annotazione_migration_contains_widened_check():
    source = SOURCE_PATH.read_text()
    for fragment in (
        "ck_raccolte_ordinary_or_correction",
        "destinazione_prevista IS NOT NULL",
        "cannot downgrade: RACCOLTA CORREZIONE annotation-only rows",
    ):
        assert fragment in source


def test_raccolta_correzione_annotazione_migration_has_no_business_dml():
    source = SOURCE_PATH.read_text()
    for statement in ("INSERT INTO", "UPDATE tpo.", "DELETE FROM"):
        assert statement not in source
    assert "id_sequences" not in source
