"""Contratti immutabili PROGRAMMA_FORNITURA Sospensione/Riattivazione V1.

Autorita: docs/architecture/PROGRAMMA_FORNITURA_SOSPENSIONE_RIATTIVAZIONE_AUTHORITY_FREEZE.md,
che implementa la proposta approvata (Owner Decision 2026-09-10) in
docs/architecture/PROGRAMMA_FORNITURA_SOSPENSIONE_RIATTIVAZIONE_PROPOSTA.md.

Due comandi governati, simmetrici a raccolta registra/correggi:
SospendiProgrammaFornitura (ATTIVO -> SOSPESO) e RiattivaProgrammaFornitura
(SOSPESO -> ATTIVO), sempre espliciti (D3: nessuna riattivazione
automatica). ``data_ripresa_prevista`` e' puramente informativa (D1): non
letta da alcun Engine, mai un trigger.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib

from ...domain.identifiers import ActorId, ProgrammaFornituraId
from .errors import InvalidProgrammaFornituraSospensioneCommandError


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidProgrammaFornituraSospensioneCommandError(
            f"{name} deve essere testo normalizzato non vuoto."
        )


def _frame(value: str | None) -> str:
    return "-1:" if value is None else f"{len(value.encode('utf-8'))}:{value}"


def _positive_version(value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise InvalidProgrammaFornituraSospensioneCommandError(
            "expected_numero_versione deve essere un intero positivo."
        )


@dataclass(frozen=True)
class ProgrammaFornituraSospensioneAuthority:
    actor: ActorId
    reason: str
    correlation_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidProgrammaFornituraSospensioneCommandError("actor non valido.")
        for name, value in (
            ("reason", self.reason), ("correlation_id", self.correlation_id),
            ("idempotency_key", self.idempotency_key),
        ):
            _text(name, value)


@dataclass(frozen=True)
class SospendiProgrammaFornitura:
    """ATTIVO -> SOSPESO. ``data_ripresa_prevista`` opzionale (D1)."""

    programma_id: ProgrammaFornituraId
    expected_numero_versione: int
    effective_at: datetime
    authority: ProgrammaFornituraSospensioneAuthority
    data_ripresa_prevista: date | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.programma_id, ProgrammaFornituraId):
            raise InvalidProgrammaFornituraSospensioneCommandError("programma_id non valido.")
        _positive_version(self.expected_numero_versione)
        if (not isinstance(self.effective_at, datetime)
                or self.effective_at.tzinfo is None
                or self.effective_at.utcoffset() is None):
            raise InvalidProgrammaFornituraSospensioneCommandError("effective_at deve essere aware.")
        if self.data_ripresa_prevista is not None and (
            not isinstance(self.data_ripresa_prevista, date)
            or isinstance(self.data_ripresa_prevista, datetime)
        ):
            raise InvalidProgrammaFornituraSospensioneCommandError(
                "data_ripresa_prevista deve essere una date valida, se presente."
            )
        if not isinstance(self.authority, ProgrammaFornituraSospensioneAuthority):
            raise InvalidProgrammaFornituraSospensioneCommandError("authority non valida.")
        object.__setattr__(self, "effective_at", self.effective_at.astimezone(timezone.utc))

    @property
    def canonical_payload(self) -> str:
        values = (
            "PROGRAMMA-FORNITURA-SOSPENDI-V1", self.programma_id.value,
            str(self.expected_numero_versione),
            self.effective_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            self.data_ripresa_prevista.isoformat() if self.data_ripresa_prevista else None,
        )
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RiattivaProgrammaFornitura:
    """SOSPESO -> ATTIVO. Sempre esplicito (D3): nessun campo legato a
    ``data_ripresa_prevista``, che non influenza in alcun modo l'esecuzione."""

    programma_id: ProgrammaFornituraId
    expected_numero_versione: int
    effective_at: datetime
    authority: ProgrammaFornituraSospensioneAuthority

    def __post_init__(self) -> None:
        if not isinstance(self.programma_id, ProgrammaFornituraId):
            raise InvalidProgrammaFornituraSospensioneCommandError("programma_id non valido.")
        _positive_version(self.expected_numero_versione)
        if (not isinstance(self.effective_at, datetime)
                or self.effective_at.tzinfo is None
                or self.effective_at.utcoffset() is None):
            raise InvalidProgrammaFornituraSospensioneCommandError("effective_at deve essere aware.")
        if not isinstance(self.authority, ProgrammaFornituraSospensioneAuthority):
            raise InvalidProgrammaFornituraSospensioneCommandError("authority non valida.")
        object.__setattr__(self, "effective_at", self.effective_at.astimezone(timezone.utc))

    @property
    def canonical_payload(self) -> str:
        values = (
            "PROGRAMMA-FORNITURA-RIATTIVA-V1", self.programma_id.value,
            str(self.expected_numero_versione),
            self.effective_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        )
        return "".join(_frame(value) for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SospendiProgrammaFornituraResult:
    programma_id: ProgrammaFornituraId
    numero_versione_precedente: int
    numero_versione: int
    stato_precedente: str
    stato: str
    data_ripresa_prevista: date | None
    effective_at: datetime
    recorded_at: datetime
    outcome: str


@dataclass(frozen=True)
class RiattivaProgrammaFornituraResult:
    programma_id: ProgrammaFornituraId
    numero_versione_precedente: int
    numero_versione: int
    stato_precedente: str
    stato: str
    effective_at: datetime
    recorded_at: datetime
    outcome: str
