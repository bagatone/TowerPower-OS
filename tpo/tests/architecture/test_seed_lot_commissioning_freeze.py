from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_implementation_preserves_seed_lot_freeze_contract():
    freeze = (ROOT / "docs/architecture/SEED_LOT_COMMISSIONING_BOUNDARY_FREEZE.md").read_text()
    migration = (ROOT / "migrations/versions/20260824_0017_seed_lot_commissioning.py").read_text()
    identifiers = (ROOT / "src/tpo_core/domain/identifiers.py").read_text()
    writer = (ROOT / "src/tpo_core/infrastructure/postgresql/seed_lot_commissioning.py").read_text()
    assert "LOTTO_PRODUZIONE" in freeze and "LottoSemeId" in identifiers
    assert 'prefix: ClassVar[str] = "LSE"' in identifiers
    assert 'sequence_name: ClassVar[str] = "LOTTO_SEME_ID"' in identifiers
    assert "seed_lot_commissioning_requests" in migration
    assert "audit_eventi" in writer
    assert "movimenti_magazzino" not in writer.lower()
    assert "semine" not in migration.lower()
