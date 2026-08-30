from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).parents[3]


def test_traceability_migration_is_linear_head():
    config = Config(str(ROOT / "migrations/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["20260830_0022"]
    revision = script.get_revision("20260826_0021")
    assert revision.down_revision == "20260825_0020"


def test_traceability_migration_contains_frozen_persistence_guards():
    source = (ROOT / "migrations/versions/20260826_0021_semina_traceability_code.py").read_text()
    for authority in (
        "uq_varieta_codice_tracciabilita",
        "ck_varieta_codice_tracciabilita",
        "uq_semine_codice_tracciabilita",
        "ck_semine_codice_tracciabilita",
        "protect_varieta_traceability_code",
        "protect_semina_constitutive_authority",
        "forward-only cut-over blocked",
        "cannot downgrade: traceable SEMINE exist",
    ):
        assert authority in source
