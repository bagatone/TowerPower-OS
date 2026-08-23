"""Narrow contract for commissioning missing permanent order-line identities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain.identifiers import ActorId


@dataclass(frozen=True)
class CommissionExistingOrderLineIdentities:
    actor: ActorId
    reason: str
    correlation_prefix: str
    expected_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise ValueError("actor non valido.")
        if any(not isinstance(v, str) or not v.strip() or v != v.strip()
               for v in (self.reason, self.correlation_prefix)):
            raise ValueError("reason/correlation_prefix non validi.")
        if not isinstance(self.expected_count, int) or isinstance(self.expected_count, bool) or self.expected_count <= 0:
            raise ValueError("expected_count non valido.")


@dataclass(frozen=True)
class ExistingOrderLineIdentityResult:
    commissioned: int
    compatible_replays: int


class ExistingOrderLineIdentityWriter(Protocol):
    def commission(self, command: CommissionExistingOrderLineIdentities) -> ExistingOrderLineIdentityResult: ...


class ExistingOrderLineIdentityCommissioningService:
    def __init__(self, writer: ExistingOrderLineIdentityWriter) -> None:
        self._writer = writer

    def commission(self, command: CommissionExistingOrderLineIdentities) -> ExistingOrderLineIdentityResult:
        if not isinstance(command, CommissionExistingOrderLineIdentities):
            raise ValueError("command non valido.")
        return self._writer.commission(command)
