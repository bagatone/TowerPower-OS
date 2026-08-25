from pathlib import Path


def test_frozen_boundary_has_implementation_components():
    root = Path(__file__).parents[2]
    freeze = (root / "docs/architecture/SEMINA_COMMISSIONING_BOUNDARY_FREEZE.md").read_text()
    assert "There is no `LOTTO_PRODUZIONE`" in freeze
    assert "ANY ANOMALY BLOCKS" in freeze
    assert "SEMINA_ID" in freeze
    assert (root / "src/tpo_core/application/semina_commissioning/service.py").is_file()
    assert (root / "src/tpo_core/infrastructure/postgresql/semina_commissioning.py").is_file()
