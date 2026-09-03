from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_implementation_preserves_semente_impiego_freeze_contract():
    freeze = (ROOT / "docs/architecture/SEMENTE_IMPIEGO_AUTHORITY_FREEZE.md").read_text()
    migration = (ROOT / "migrations/versions/20260903_0024_semente_impiego_commissioning.py").read_text()
    identifiers = (ROOT / "src/tpo_core/domain/identifiers.py").read_text()
    writer = (ROOT / "src/tpo_core/infrastructure/postgresql/semente_impiego_commissioning.py").read_text()
    assert "No public technical ID is introduced" in freeze
    assert "class SementeImpiegoId" not in identifiers
    assert '"SEMENTE_IMPIEGO_ID"' not in identifiers
    assert "semente_impiego_commissioning_requests" in migration
    assert "audit_eventi" in writer
    assert "entity_public_id,operation,reason,\n" in writer
    assert "'SEMENTE_IMPIEGO',NULL,'INSERT'" in writer
    assert "lotti_seme" not in migration.lower()
    assert "semine" not in migration.lower()


def test_semente_impiego_commissioning_never_creates_semente_or_cultivar_uso():
    writer = (ROOT / "src/tpo_core/infrastructure/postgresql/semente_impiego_commissioning.py").read_text()
    for forbidden in ("insert into tpo.sementi", "insert into tpo.cultivar_usi", "insert into tpo.protocolli"):
        assert forbidden not in writer.lower()


def test_semente_impiego_resolution_requires_approved_valid_protocol_context():
    writer = (ROOT / "src/tpo_core/infrastructure/postgresql/semente_impiego_commissioning.py").read_text()
    assert "stato_approvazione='APPROVATA'" in writer
    assert "cu.stato_validazione='APPROVATA'" in writer
    assert "c.stato='ATTIVA'" in writer
    assert "v.stato='ATTIVA'" in writer


def test_semente_impiego_constitutive_pair_is_immutable_after_creation():
    migration = (ROOT / "migrations/versions/20260903_0024_semente_impiego_commissioning.py").read_text()
    assert "protect_semente_impiego_constitutive_authority" in migration
    assert "NEW.semente_id IS DISTINCT FROM OLD.semente_id" in migration
    assert "NEW.cultivar_uso_id IS DISTINCT FROM OLD.cultivar_uso_id" in migration


def test_ultima_revisione_is_writer_owned_current_date_never_caller_input():
    writer = (ROOT / "src/tpo_core/infrastructure/postgresql/semente_impiego_commissioning.py").read_text()
    models = (ROOT / "src/tpo_core/application/semente_impiego_commissioning/models.py").read_text()
    assert "VALUES (%s,%s,%s,%s,%s,CURRENT_DATE,%s,CURRENT_TIMESTAMP,%s,0)" in writer
    command_class = models.split("class CommissionSementeImpiego:")[1].split("class CommissionSementeImpiegoResult")[0]
    assert "ultima_revisione" not in command_class
