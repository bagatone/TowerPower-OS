"""Contratti immutabili Semina Lifecycle Event Authority V1."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib

from ...domain.identifiers import ActorId, SeminaId
from ...domain.states import SeminaFinalOutcome, SeminaState
from ..semina_commissioning.models import SeminaFactSource
from .errors import (
    InvalidSeminaLifecycleCommandError, SeminaFinalOutcomeForbiddenError,
    SeminaFinalOutcomeRequiredError, SeminaLifecycleProvenanceInvalidError,
    SeminaLifecycleTimestampInvalidError, SeminaTransitionInvalidError,
)


ALLOWED_EDGES = frozenset({
    (SeminaState.AVVIATA, SeminaState.GERMINAZIONE),
    (SeminaState.GERMINAZIONE, SeminaState.LUCE),
    (SeminaState.LUCE, SeminaState.CRESCITA),
    (SeminaState.CRESCITA, SeminaState.PRONTA_ALLA_RACCOLTA),
    *((state, SeminaState.CHIUSA) for state in SeminaState if state is not SeminaState.CHIUSA),
})


def validate_transition(current: SeminaState, target: SeminaState) -> None:
    if not isinstance(current, SeminaState) or not isinstance(target, SeminaState):
        raise SeminaTransitionInvalidError("Stato lifecycle non valido.")
    if (current, target) not in ALLOWED_EDGES:
        raise SeminaTransitionInvalidError("Transizione SEMINA non consentita.")


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidSeminaLifecycleCommandError(f"{name} deve essere testo normalizzato non vuoto.")


@dataclass(frozen=True)
class SeminaLifecycleAuthority:
    actor: ActorId
    reason: str
    correlation_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidSeminaLifecycleCommandError("actor non valido.")
        for name, value in (("reason", self.reason), ("correlation_id", self.correlation_id),
                            ("idempotency_key", self.idempotency_key)):
            _text(name, value)


@dataclass(frozen=True)
class TransitionSemina:
    semina_public_id: SeminaId
    expected_semina_version: int
    target_state: SeminaState
    effective_at: datetime
    final_outcome: SeminaFinalOutcome | None
    provenance: tuple[tuple[str, SeminaFactSource], ...]
    authority: SeminaLifecycleAuthority

    def __post_init__(self) -> None:
        if not isinstance(self.semina_public_id, SeminaId):
            raise InvalidSeminaLifecycleCommandError("SEM non valido.")
        if (not isinstance(self.expected_semina_version, int)
                or isinstance(self.expected_semina_version, bool)
                or self.expected_semina_version < 0):
            raise InvalidSeminaLifecycleCommandError("expected_semina_version non valido.")
        if not isinstance(self.target_state, SeminaState):
            raise InvalidSeminaLifecycleCommandError("target_state non valido.")
        if (not isinstance(self.effective_at, datetime) or self.effective_at.tzinfo is None
                or self.effective_at.utcoffset() is None):
            raise SeminaLifecycleTimestampInvalidError("effective_at deve avere timezone.")
        if self.target_state is SeminaState.CHIUSA:
            if not isinstance(self.final_outcome, SeminaFinalOutcome):
                raise SeminaFinalOutcomeRequiredError("CHIUSA richiede esito_finale.")
        elif self.final_outcome is not None:
            raise SeminaFinalOutcomeForbiddenError("Esito finale vietato per stato attivo.")
        if not isinstance(self.authority, SeminaLifecycleAuthority):
            raise InvalidSeminaLifecycleCommandError("authority non valida.")
        try:
            mapping = dict(self.provenance)
        except Exception as exc:
            raise SeminaLifecycleProvenanceInvalidError("provenance non valida.") from exc
        required = {"target_state", "effective_at"}
        if self.target_state is SeminaState.CHIUSA:
            required.add("final_outcome")
        if (len(mapping) != len(self.provenance) or set(mapping) != required
                or not all(isinstance(source, SeminaFactSource) for source in mapping.values())):
            raise SeminaLifecycleProvenanceInvalidError("provenance lifecycle incompleta o non valida.")
        object.__setattr__(self, "effective_at", self.effective_at.astimezone(timezone.utc))
        object.__setattr__(self, "provenance", tuple(sorted(mapping.items())))

    @property
    def canonical_payload(self) -> str:
        values = (
            "SEMINA-LIFECYCLE-TRANSITION-V1", self.semina_public_id.value,
            str(self.expected_semina_version), self.target_state.value,
            self.effective_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            self.final_outcome.value if self.final_outcome else None,
            *(f"{field}={source.value}" for field, source in self.provenance),
        )
        return "".join("-1:" if value is None else f"{len(value.encode('utf-8'))}:{value}" for value in values)

    @property
    def canonical_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload.encode()).hexdigest()


@dataclass(frozen=True)
class TransitionSeminaResult:
    semina_public_id: SeminaId
    previous_state: SeminaState
    resulting_state: SeminaState
    final_outcome: SeminaFinalOutcome | None
    effective_at: datetime
    recorded_at: datetime
    version_before: int
    version_after: int
    outcome: str
