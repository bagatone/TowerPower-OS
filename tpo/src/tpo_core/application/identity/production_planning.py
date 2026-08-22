"""Mapping Identity provider-neutral autorizzato per Production Planning."""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from ...domain.identifiers import (
    AllocazioneId,
    PermanentId,
    PianoProduzioneId,
    RevisionePianoProduzioneId,
    RigaPianoSeminaId,
    RunPianificazioneProduzioneId,
)
from .errors import InvalidIdentifierSequenceError


PRODUCTION_PLANNING_IDENTIFIER_TYPES: tuple[type[PermanentId], ...] = (
    AllocazioneId,
    PianoProduzioneId,
    RevisionePianoProduzioneId,
    RigaPianoSeminaId,
    RunPianificazioneProduzioneId,
)

PRODUCTION_PLANNING_SEQUENCE_TYPES: Mapping[str, type[PermanentId]] = MappingProxyType(
    {
        identifier_type.sequence_name: identifier_type
        for identifier_type in PRODUCTION_PLANNING_IDENTIFIER_TYPES
    }
)


def production_planning_identifier_type(sequence_name: str) -> type[PermanentId]:
    """Risolve esclusivamente una sequence congelata, senza fallback."""

    if not isinstance(sequence_name, str):
        raise InvalidIdentifierSequenceError(
            "Production Planning sequence name non valida."
        )
    try:
        return PRODUCTION_PLANNING_SEQUENCE_TYPES[sequence_name]
    except KeyError as exc:
        raise InvalidIdentifierSequenceError(
            f"Production Planning sequence non autorizzata: {sequence_name!r}."
        ) from exc
