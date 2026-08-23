"""Provider-neutral incremental Identity commissioning contract."""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from src.tpo_core.application.identity import (
    CommissionedIdentityRegistration,
    CommissionIdentityRegistration,
    IdentifierSequence,
    IdentityRegistrationCommissioningService,
    InvalidIdentityCommissioningCommandError,
)
from src.tpo_core.application.identity.production_planning import (
    PRODUCTION_PLANNING_SEQUENCE_TYPES,
)
from src.tpo_core.domain.identifiers import (
    ActorId,
    PermanentId,
    RunPianificazioneProduzioneId,
)


class Writer:
    def __init__(self) -> None:
        self.commands = []

    def commission(self, command):
        self.commands.append(command)
        return CommissionedIdentityRegistration(
            command,
            IdentifierSequence(command.permanent_id_type.__name__, command.prefix, 1, 0),
            datetime(2026, 8, 23, tzinfo=timezone.utc),
        )


def command() -> CommissionIdentityRegistration:
    return CommissionIdentityRegistration(
        "RUN_PIANIFICAZIONE_PRODUZIONE_ID",
        RunPianificazioneProduzioneId,
        "RPP",
        ActorId("tpo.identity-commissioner"),
    )


def test_service_delegates_typed_command_without_allocating() -> None:
    writer = Writer()
    result = IdentityRegistrationCommissioningService(writer).commission(command())
    assert writer.commands == [command()]
    assert result.sequence == IdentifierSequence(
        "RunPianificazioneProduzioneId", "RPP", 1, 0
    )


@pytest.mark.parametrize(
    "change",
    (
        {"sequence_name": "WRONG"},
        {"prefix": "BAD"},
        {"permanent_id_type": PermanentId},
        {"permanent_id_type": object},
    ),
)
def test_command_must_match_frozen_permanent_id_authority(change) -> None:
    with pytest.raises(InvalidIdentityCommissioningCommandError):
        replace(command(), **change)


def test_all_planning_commands_reuse_central_frozen_mapping() -> None:
    commands = tuple(
        CommissionIdentityRegistration(
            name, identifier_type, identifier_type.prefix,
            ActorId("tpo.identity-commissioner"),
        )
        for name, identifier_type in PRODUCTION_PLANNING_SEQUENCE_TYPES.items()
    )
    assert len(commands) == 5
    assert {item.sequence_name for item in commands} == set(
        PRODUCTION_PLANNING_SEQUENCE_TYPES
    )
