"""Immutable models for explicit Production Planning policy commissioning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from ...domain.identifiers import ActorId
from .errors import InvalidPolicyCommissioningCommandError


_BUFFER_TYPES = frozenset({"NONE", "PERCENTAGE", "ABSOLUTE_SET"})
_PRIORITY_POLICY_V1 = "DELIVERY_THEN_PUBLIC_ID"
_ALGORITHM_V1 = "production-planning-v1"
_HARVEST_STRATEGY_V1 = "EARLIEST_APPROVED_WINDOW"


def _text(name: str, value: object, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidPolicyCommissioningCommandError(
            f"{name} deve essere testo normalizzato non vuoto."
        )


def _buffer(value: object | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, (float, bool)):
        raise InvalidPolicyCommissioningCommandError(
            "quantitative_buffer_value non accetta float o booleani."
        )
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)  # type: ignore[arg-type]
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidPolicyCommissioningCommandError(
            "quantitative_buffer_value deve essere Decimal."
        ) from exc
    if not parsed.is_finite() or parsed.as_tuple().exponent < -6:
        raise InvalidPolicyCommissioningCommandError(
            "quantitative_buffer_value deve essere finito con massimo sei decimali."
        )
    return parsed


@dataclass(frozen=True)
class CommissionProductionPlanningPolicyCommand:
    policy_set_code: str
    version: int
    valid_from: date
    valid_to: date | None
    priority_policy_code: str
    planning_algorithm_version: str
    quantitative_buffer_type: str
    quantitative_buffer_value: Decimal | None
    harvest_target_strategy: str
    actor: ActorId
    provenance: str
    evidence: str | None

    def __post_init__(self) -> None:
        _text("policy_set_code", self.policy_set_code)
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version <= 0:
            raise InvalidPolicyCommissioningCommandError("version deve essere positiva.")
        if not isinstance(self.valid_from, date) or isinstance(self.valid_from, datetime):
            raise InvalidPolicyCommissioningCommandError("valid_from deve essere una data.")
        if self.valid_to is not None and (
            not isinstance(self.valid_to, date)
            or isinstance(self.valid_to, datetime)
            or self.valid_to <= self.valid_from
        ):
            raise InvalidPolicyCommissioningCommandError(
                "valid_to deve essere successiva a valid_from."
            )
        if self.priority_policy_code != _PRIORITY_POLICY_V1:
            raise InvalidPolicyCommissioningCommandError("priority_policy_code V1 non valido.")
        if self.planning_algorithm_version != _ALGORITHM_V1:
            raise InvalidPolicyCommissioningCommandError(
                "planning_algorithm_version V1 non valida."
            )
        if self.harvest_target_strategy != _HARVEST_STRATEGY_V1:
            raise InvalidPolicyCommissioningCommandError(
                "harvest_target_strategy V1 non valida."
            )
        if self.quantitative_buffer_type not in _BUFFER_TYPES:
            raise InvalidPolicyCommissioningCommandError(
                "quantitative_buffer_type non valido."
            )
        parsed_buffer = _buffer(self.quantitative_buffer_value)
        if self.quantitative_buffer_type == "NONE":
            if parsed_buffer is not None:
                raise InvalidPolicyCommissioningCommandError(
                    "NONE richiede quantitative_buffer_value NULL."
                )
        elif parsed_buffer is None or parsed_buffer < 0 or (
            self.quantitative_buffer_type == "PERCENTAGE" and parsed_buffer > 100
        ):
            raise InvalidPolicyCommissioningCommandError(
                "quantitative_buffer_value non coerente con il tipo."
            )
        object.__setattr__(self, "quantitative_buffer_value", parsed_buffer)
        if not isinstance(self.actor, ActorId):
            raise InvalidPolicyCommissioningCommandError("actor non valido.")
        _text("provenance", self.provenance)
        _text("evidence", self.evidence, optional=True)


@dataclass(frozen=True)
class CommissionedProductionPlanningPolicy:
    command: CommissionProductionPlanningPolicyCommand
    approved_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.command, CommissionProductionPlanningPolicyCommand):
            raise InvalidPolicyCommissioningCommandError("command approvato non valido.")
        if (
            not isinstance(self.approved_at, datetime)
            or self.approved_at.tzinfo is None
            or self.approved_at.utcoffset() is None
        ):
            raise InvalidPolicyCommissioningCommandError(
                "approved_at deve essere timezone-aware."
            )
