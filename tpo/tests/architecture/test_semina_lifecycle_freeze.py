from pathlib import Path


FREEZE = Path(__file__).parents[2] / "docs/architecture/SEMINA_LIFECYCLE_EVENT_AUTHORITY_FREEZE.md"


def test_lifecycle_freeze_is_normative_and_complete():
    text = FREEZE.read_text(encoding="utf-8")
    required = (
        "SEMINA LIFECYCLE EVENT AUTHORITY V1",
        "AVVIATA → GERMINAZIONE", "GERMINAZIONE → LUCE", "LUCE → CRESCITA",
        "CRESCITA → PRONTA_ALLA_RACCOLTA", "Every active state may also transition",
        "effective_at >= semina.data_avvio",
        "effective_at > latest_lifecycle_effective_at",
        "does not introduce mandatory `observed_at`", "append-only",
        "same key + same payload", "same key + different payload",
        "different key + already physically applied transition",
        "does not invoke, create, replace or revise Production Planning",
        "Experimental Production Authority",
    )
    assert all(item in text for item in required)
    assert "public event ID, prefix, PermanentId type or Identity sequence" in text


def test_implementation_does_not_add_lifecycle_public_identity():
    identifiers = (Path(__file__).parents[2] / "src/tpo_core/domain/identifiers.py").read_text()
    assert "LifecycleEventId" not in identifiers
