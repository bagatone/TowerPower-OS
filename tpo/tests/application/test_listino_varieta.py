from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.listino_varieta import (
    ImpostaPrezzoListinoVarieta, ImpostaPrezzoListinoVarietaResult,
    ListinoVarietaAuthority, ListinoVarietaService,
)
from src.tpo_core.application.listino_varieta.errors import InvalidListinoVarietaCommandError
from src.tpo_core.domain.identifiers import ActorId, VarietaId

AUTHORITY = ListinoVarietaAuthority(ActorId("owner"), "Aggiornamento listino reale", "corr-listino-1")


def command(*, prezzo="12.50", aliquota="7", authority=AUTHORITY):
    return ImpostaPrezzoListinoVarieta(
        VarietaId("VAR-000001"), Decimal(prezzo), Decimal(aliquota), authority,
    )


def test_authority_accepts_typed_actor_and_normalized_text():
    authority = ListinoVarietaAuthority(ActorId("owner"), "reason", "corr-1")
    assert authority.actor == ActorId("owner")
    assert authority.reason == "reason"
    assert authority.correlation_id == "corr-1"


def test_authority_rejects_non_actor_id():
    with pytest.raises(InvalidListinoVarietaCommandError):
        ListinoVarietaAuthority("owner", "reason", "corr-1")


@pytest.mark.parametrize("value", ["", " ", "  spaced  ", 123])
def test_authority_rejects_missing_or_non_normalized_reason(value):
    with pytest.raises((InvalidListinoVarietaCommandError, ValueError)):
        ListinoVarietaAuthority(ActorId("owner"), value, "corr-1")


@pytest.mark.parametrize("value", ["", " ", "  spaced  ", None])
def test_authority_rejects_missing_or_non_normalized_correlation_id(value):
    with pytest.raises((InvalidListinoVarietaCommandError, ValueError)):
        ListinoVarietaAuthority(ActorId("owner"), "reason", value)


def test_command_accepts_valid_price_and_rate():
    cmd = command()
    assert cmd.varieta_id == VarietaId("VAR-000001")
    assert cmd.prezzo_unitario == Decimal("12.50")
    assert cmd.aliquota_igic == Decimal("7")
    assert cmd.authority == AUTHORITY


def test_command_accepts_zero_price_and_rate_boundaries():
    assert command(prezzo="0", aliquota="0").prezzo_unitario == Decimal("0")
    assert command(prezzo="0", aliquota="100").aliquota_igic == Decimal("100")


def test_command_rejects_non_varieta_id():
    with pytest.raises(InvalidListinoVarietaCommandError):
        ImpostaPrezzoListinoVarieta("VAR-000001", Decimal("1"), Decimal("7"), AUTHORITY)


@pytest.mark.parametrize("value", [Decimal("-0.01"), Decimal("-100")])
def test_command_rejects_negative_price(value):
    with pytest.raises(InvalidListinoVarietaCommandError):
        ImpostaPrezzoListinoVarieta(VarietaId("VAR-000001"), value, Decimal("7"), AUTHORITY)


@pytest.mark.parametrize("value", ["12.50", 12.5, 1250])
def test_command_rejects_non_decimal_price(value):
    with pytest.raises(InvalidListinoVarietaCommandError):
        ImpostaPrezzoListinoVarieta(VarietaId("VAR-000001"), value, Decimal("7"), AUTHORITY)


@pytest.mark.parametrize("value", [Decimal("-0.01"), Decimal("100.01"), Decimal("101")])
def test_command_rejects_out_of_range_rate(value):
    with pytest.raises(InvalidListinoVarietaCommandError):
        ImpostaPrezzoListinoVarieta(VarietaId("VAR-000001"), Decimal("1"), value, AUTHORITY)


@pytest.mark.parametrize("value", ["7", 7.0])
def test_command_rejects_non_decimal_rate(value):
    with pytest.raises(InvalidListinoVarietaCommandError):
        ImpostaPrezzoListinoVarieta(VarietaId("VAR-000001"), Decimal("1"), value, AUTHORITY)


def test_command_rejects_non_authority():
    with pytest.raises(InvalidListinoVarietaCommandError):
        ImpostaPrezzoListinoVarieta(VarietaId("VAR-000001"), Decimal("1"), Decimal("7"), "authority")


def test_result_outcome_distinguishes_inserted_and_updated():
    inserted = ImpostaPrezzoListinoVarietaResult(
        "VAR-000001", Decimal("1"), Decimal("7"), datetime(2026, 9, 4, tzinfo=timezone.utc),
        inserted=True,
    )
    updated = ImpostaPrezzoListinoVarietaResult(
        "VAR-000001", Decimal("1"), Decimal("7"), datetime(2026, 9, 4, tzinfo=timezone.utc),
        inserted=False, updated=True,
    )
    assert inserted.outcome == "INSERTED"
    assert updated.outcome == "UPDATED"


@pytest.mark.parametrize(("inserted", "updated"), [(True, True), (False, False)])
def test_result_rejects_ambiguous_outcome(inserted, updated):
    with pytest.raises(InvalidListinoVarietaCommandError):
        ImpostaPrezzoListinoVarietaResult(
            "VAR-000001", Decimal("1"), Decimal("7"),
            datetime(2026, 9, 4, tzinfo=timezone.utc), inserted=inserted, updated=updated,
        )


class _Writer:
    def __init__(self, result=None):
        self.commands = []
        self._result = result or ImpostaPrezzoListinoVarietaResult(
            "VAR-000001", Decimal("1"), Decimal("7"),
            datetime(2026, 9, 4, tzinfo=timezone.utc), inserted=True,
        )

    def imposta_prezzo(self, command):
        self.commands.append(command)
        return self._result


def test_service_delegates_valid_command_to_writer():
    writer = _Writer()
    service = ListinoVarietaService(writer)
    cmd = command()
    result = service.imposta_prezzo(cmd)
    assert writer.commands == [cmd]
    assert result.varieta_public_id == "VAR-000001"


def test_service_rejects_non_command_input():
    service = ListinoVarietaService(_Writer())
    with pytest.raises(InvalidListinoVarietaCommandError):
        service.imposta_prezzo("not-a-command")
