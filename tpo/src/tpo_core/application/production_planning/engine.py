"""Calcolo puro e provider-neutral del Production Planning V1."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from .errors import ProductionPlanningError
from .models import (
    HARVEST_TARGET_STRATEGY_V1,
    PRODUCTION_PLANNING_ALGORITHM_VERSION_V1,
    PRODUCTION_PLANNING_PRIORITY_POLICY_V1,
    DemandSnapshot,
    PlanningCandidate,
    PlanningInputSnapshot,
    PlanningPolicySnapshot,
    ProductionKnowledgeSnapshot,
)
from ...domain.time_reference import OFFICIAL_TIMEZONE



class ProductionPlanningEngine:
    """Trasforma uno snapshot immutabile in candidati, senza side effect."""

    def calculate(self, snapshot: PlanningInputSnapshot) -> list[PlanningCandidate]:
        if not isinstance(snapshot, PlanningInputSnapshot):
            raise ProductionPlanningError(
                "PLANNING_INPUT_INVALID", "INVALID_SNAPSHOT", "Snapshot Planning non valido."
            )
        _validate_policy(snapshot.policy)
        candidates = [self._candidate(demand, snapshot) for demand in snapshot.demands]
        return sorted(candidates, key=lambda item: _demand_order(item.demand))

    def _candidate(
        self, demand: DemandSnapshot, snapshot: PlanningInputSnapshot
    ) -> PlanningCandidate:
        matches: list[tuple[ProductionKnowledgeSnapshot, _Timeline]] = []
        for knowledge in snapshot.knowledge:
            if knowledge.variety_public_id != demand.variety_public_id:
                continue
            if knowledge.approval_state != "APPROVATA":
                continue
            timeline = _timeline(demand.delivery_date, knowledge)
            sowing_date = timeline.sowing_at.astimezone(OFFICIAL_TIMEZONE).date()
            if knowledge.valid_from <= sowing_date and (
                knowledge.valid_to is None or sowing_date < knowledge.valid_to
            ):
                matches.append((knowledge, timeline))

        if not matches:
            raise ProductionPlanningError(
                "PRODUCTION_KNOWLEDGE_INVALID",
                "PROTOCOL_NOT_AVAILABLE",
                "Nessun protocollo approvato e valido per la domanda.",
            )
        if len(matches) != 1:
            raise ProductionPlanningError(
                "PRODUCTION_KNOWLEDGE_INVALID",
                "PROTOCOL_AMBIGUOUS",
                "Piu protocolli approvati e validi per la domanda.",
            )

        knowledge, timeline = matches[0]
        return PlanningCandidate(
            demand=demand,
            knowledge=knowledge,
            harvest_target_at=timeline.harvest_target_at,
            sowing_at=timeline.sowing_at,
            light_at=timeline.light_at,
            hydration_at=timeline.hydration_at,
            provenance=f"{demand.provenance}|{knowledge.provenance}",
        )


def calculate(snapshot: PlanningInputSnapshot) -> list[PlanningCandidate]:
    """Ingresso funzionale equivalente all'engine stateless."""

    return ProductionPlanningEngine().calculate(snapshot)


class _Timeline:
    def __init__(
        self,
        *,
        harvest_target_at: datetime,
        sowing_at: datetime,
        light_at: datetime,
        hydration_at: datetime,
    ) -> None:
        self.harvest_target_at = harvest_target_at
        self.sowing_at = sowing_at
        self.light_at = light_at
        self.hydration_at = hydration_at


def _timeline(delivery_date: date, knowledge: ProductionKnowledgeSnapshot) -> _Timeline:
    harvest_date = delivery_date - timedelta(days=knowledge.harvest_max_lead_days)
    harvest = _strict_local_datetime(harvest_date, knowledge.target_harvest_time)
    sowing = harvest - timedelta(
        days=knowledge.germination_days + knowledge.light_growth_days,
        minutes=knowledge.temporal_buffer_minutes,
    )
    if sowing.astimezone(OFFICIAL_TIMEZONE).time().replace(tzinfo=None) != knowledge.planned_sowing_time:
        raise ProductionPlanningError(
            "PRODUCTION_KNOWLEDGE_INVALID",
            "PROTOCOL_TIMELINE_INCOHERENT",
            "Orario di semina calcolato incoerente con il protocollo.",
        )
    hydration_minutes = knowledge.hydration_hours * Decimal(60)
    if hydration_minutes != hydration_minutes.to_integral_value():
        raise ProductionPlanningError(
            "PRODUCTION_KNOWLEDGE_INVALID",
            "PROTOCOL_TIMELINE_INCOHERENT",
            "Idratazione non rappresentabile con precisione al minuto.",
        )
    light = sowing + timedelta(days=knowledge.germination_days)
    hydration = sowing - timedelta(minutes=int(hydration_minutes))
    if not hydration <= sowing <= light <= harvest:
        raise ProductionPlanningError(
            "PRODUCTION_KNOWLEDGE_INVALID",
            "PROTOCOL_TIMELINE_INCOHERENT",
            "Timeline produttiva incoerente.",
        )
    return _Timeline(
        harvest_target_at=harvest,
        sowing_at=sowing,
        light_at=light,
        hydration_at=hydration,
    )


def _strict_local_datetime(local_date: date, local_time) -> datetime:
    naive = datetime.combine(local_date, local_time)
    candidates = []
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=OFFICIAL_TIMEZONE, fold=fold)
        round_trip = candidate.astimezone(UTC).astimezone(OFFICIAL_TIMEZONE).replace(tzinfo=None)
        if round_trip == naive:
            candidates.append(candidate)
    offsets = {candidate.utcoffset() for candidate in candidates}
    if not candidates or len(offsets) != 1:
        raise ProductionPlanningError(
            "PRODUCTION_KNOWLEDGE_INVALID",
            "PROTOCOL_LOCAL_TIME_INVALID",
            "Orario locale protocollo ambiguo o inesistente.",
        )
    return candidates[0].replace(second=0, microsecond=0)


def _validate_policy(policy: PlanningPolicySnapshot) -> None:
    if (
        policy.priority_policy_code != PRODUCTION_PLANNING_PRIORITY_POLICY_V1
        or policy.algorithm_version != PRODUCTION_PLANNING_ALGORITHM_VERSION_V1
        or policy.harvest_target_strategy != HARVEST_TARGET_STRATEGY_V1
    ):
        raise ProductionPlanningError(
            "PLANNING_INPUT_INVALID",
            "UNSUPPORTED_PLANNING_POLICY",
            "Planning Policy V1 non supportata.",
        )


def _demand_order(demand: DemandSnapshot) -> tuple[object, ...]:
    priority = demand.commercial_priority
    return (
        demand.delivery_date,
        priority is None,
        priority if priority is not None else 0,
        demand.order_public_id.value,
        demand.order_line_public_id.value,
    )
