from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_implementation_preserves_semente_freeze_contract():
    freeze = (ROOT / "docs/architecture/SEMENTE_AUTHORITY_FREEZE.md").read_text()
    migration = (ROOT / "migrations/versions/20260903_0023_semente_commissioning.py").read_text()
    identifiers = (ROOT / "src/tpo_core/domain/identifiers.py").read_text()
    writer = (ROOT / "src/tpo_core/infrastructure/postgresql/semente_commissioning.py").read_text()
    assert "SEMENTE V1 does not introduce a public technical ID" in freeze
    assert "class SementeId" not in identifiers
    assert '"SEMENTE_ID"' not in identifiers
    assert "semente_commissioning_requests" in migration
    assert "audit_eventi" in writer
    assert "entity_public_id,operation,reason,\n" in writer
    assert "'SEMENTE',NULL,'INSERT'" in writer
    assert "lotti_seme" not in migration.lower()
    assert "semine" not in migration.lower()
    assert "articoli" not in migration.lower()


def test_semente_commissioning_never_creates_semente_impiego_or_articolo():
    writer = (ROOT / "src/tpo_core/infrastructure/postgresql/semente_commissioning.py").read_text()
    service = (ROOT / "src/tpo_core/application/semente_commissioning/service.py").read_text()
    for forbidden in ("semente_impieghi", "articoli", "lotti_seme"):
        assert forbidden not in writer.lower()
        assert forbidden not in service.lower()


def test_semente_constitutive_fields_are_immutable_after_creation():
    writer = (ROOT / "src/tpo_core/infrastructure/postgresql/semente_commissioning.py").read_text()
    migration = (ROOT / "migrations/versions/20260903_0023_semente_commissioning.py").read_text()
    assert "UPDATE tpo.sementi" not in writer
    assert "protect_semente_constitutive_authority" in migration
