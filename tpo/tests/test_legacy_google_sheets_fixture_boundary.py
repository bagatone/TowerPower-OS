from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_does_not_reference_legacy_google_sheets_test_fixture() -> None:
    forbidden = (
        "tests/fixtures/legacy_google_sheets",
        "legacy_sheets_schema.md",
    )
    violations = []
    for path in sorted((ROOT / "src").rglob("*")):
        if not path.is_file() or path.suffix not in {".py", ".md", ".toml", ".yaml", ".yml"}:
            continue
        content = path.read_text(encoding="utf-8")
        if any(marker in content for marker in forbidden):
            violations.append(path.relative_to(ROOT).as_posix())
    assert violations == []
