from datetime import datetime, timezone

import pytest

from src.tpo_core.domain.errors import InvalidTraceabilityCodeError
from src.tpo_core.domain.traceability import SeminaTraceabilityCode, VarietyTraceabilityCode


def test_variety_code_is_exactly_three_uppercase_ascii_letters():
    assert VarietyTraceabilityCode("CIL").value == "CIL"
    for value in ("CI", "CILA", "cil", "C1L", "ÁFI", " CIL"):
        with pytest.raises(InvalidTraceabilityCodeError):
            VarietyTraceabilityCode(value)


def test_semina_code_uses_canary_local_physical_date():
    code = SeminaTraceabilityCode.build(
        VarietyTraceabilityCode("CIL"), datetime(2026, 8, 26, 23, 30, tzinfo=timezone.utc), "A"
    )
    assert code.value == "CIL-2708-A"


def test_semina_code_rejects_bad_grammar_and_impossible_calendar_date():
    for value in ("CIL2608A", "cil-2608-A", "CIL-0008-A", "CIL-3102-A", "CIL-2608-AA"):
        with pytest.raises(InvalidTraceabilityCodeError):
            SeminaTraceabilityCode(value)
