"""Frozen automated Production Planning invocation contract."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "docs/architecture/AUTOMATED_PRODUCTION_PLANNING_INVOCATION_FREEZE.md"
OPERATIONAL_FREEZE = ROOT / "docs/architecture/AUTOMATED_OPERATIONAL_SCHEDULING_FREEZE.md"


def test_freeze_fixes_initial_occurrence_identity_and_replay_contract():
    text = FREEZE.read_text(encoding="utf-8")
    for value in (
        "06:30 Atlantic/Canary",
        "`DEFAULT`",
        "`1`",
        "`tpo.production-planning-scheduler`",
        "`Automated Production Planning V1`",
        "`production-planning-auto-v1:<canonical-business-at>`",
        "Automated REPLAN is unsupported",
        "There is no automatic retry and no catch-up",
        "CLI",
        "Google",
    ):
        assert value in text


def test_atlantic_canary_canonical_offsets_are_dst_aware():
    canary = ZoneInfo("Atlantic/Canary")
    winter = datetime(2026, 1, 15, 6, 30, tzinfo=canary).isoformat(timespec="seconds")
    summer = datetime(2026, 8, 23, 6, 30, tzinfo=canary).isoformat(timespec="seconds")
    assert winter == "2026-01-15T06:30:00+00:00"
    assert summer == "2026-08-23T06:30:00+01:00"


def test_dst_invalid_time_and_operational_dependency_fail_closed_contract():
    text = FREEZE.read_text(encoding="utf-8")
    assert "ambiguous or nonexistent" in text
    assert "fails closed before the CLI" in text
    assert "no hard dependency" in text
    assert "already\ncommitted before that PostgreSQL snapshot begins" in text


def test_existing_operational_scheduling_occurrence_is_unchanged():
    text = OPERATIONAL_FREEZE.read_text(encoding="utf-8")
    assert "06:00 Atlantic/Canary" in text
    assert "tpo schedule execute" in text


def test_5_3b_automation_adds_no_schema_or_business_seed():
    assert (ROOT / "scripts/run_production_planning_schedule.sh").is_file()
    assert (ROOT / "deploy/macos/com.towerpower.production-planning-scheduler.plist").is_file()
    migration_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "migrations/versions").glob("*.py")
    )
    assert "Owner-approved commissioning for Production Planning V1" not in migration_sources
