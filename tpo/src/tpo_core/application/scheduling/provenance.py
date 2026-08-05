"""Riferimenti applicativi provider-neutral all'origine delle righe ORDINE."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.errors import InvariantViolationError
from ...domain.entities.programma_fornitura import ProgrammaFornitura, RigaProgrammaFornitura
from ...domain.identifiers import ProgrammaFornituraId


@dataclass(frozen=True)
class OrderLineProvenance:
    """Individua una riga di una versione PROGRAMMA e la riga ORDINE prodotta."""

    programma_fornitura_id: ProgrammaFornituraId
    programma_version: int
    programma_line_position: int
    order_line_position: int

    def __post_init__(self) -> None:
        if not isinstance(self.programma_fornitura_id, ProgrammaFornituraId):
            raise InvariantViolationError(
                "La provenance richiede un ProgrammaFornituraId valido."
            )
        for name in (
            "programma_version",
            "programma_line_position",
            "order_line_position",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise InvariantViolationError(f"{name} deve essere un intero positivo.")


@dataclass(frozen=True)
class VersionedProgramLine:
    """Associa una riga di dominio alla sua posizione autorevole persistente."""

    position: int
    line: RigaProgrammaFornitura

    def __post_init__(self) -> None:
        if isinstance(self.position, bool) or not isinstance(self.position, int) or self.position <= 0:
            raise InvariantViolationError("position deve essere un intero positivo.")
        if not isinstance(self.line, RigaProgrammaFornitura):
            raise InvariantViolationError("line deve essere una RigaProgrammaFornitura.")


@dataclass(frozen=True)
class VersionedProgrammaFornitura:
    """Snapshot applicativo versionato richiesto dallo Scheduling autorevole."""

    programma: ProgrammaFornitura
    version: int
    lines: tuple[VersionedProgramLine, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.programma, ProgrammaFornitura):
            raise InvariantViolationError("programma deve essere un ProgrammaFornitura.")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version <= 0:
            raise InvariantViolationError("version deve essere un intero positivo.")
        if not isinstance(self.lines, tuple) or any(
            not isinstance(item, VersionedProgramLine) for item in self.lines
        ):
            raise InvariantViolationError("lines deve essere una tuple di locator validi.")
        if tuple(item.line for item in self.lines) != self.programma.righe:
            raise InvariantViolationError("I locator non coincidono con le righe del programma.")
        positions = tuple(item.position for item in self.lines)
        if len(set(positions)) != len(positions):
            raise InvariantViolationError("Le posizioni autorevoli non possono essere duplicate.")
