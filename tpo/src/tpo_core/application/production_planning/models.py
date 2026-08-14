"""Modelli immutabili provider-neutral del Production Planning V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
import hashlib
import re

from ...domain.identifiers import ActorId
from ...domain.quantities import UnitOfMeasure
from ...domain.states import OrdineState, SeminaState
from .errors import FROZEN_FAILURE_CATEGORIES, InvalidProductionPlanningModelError


REPLANNING_REASONS = frozenset(
    {"DEMAND_CHANGED", "DELIVERY_CHANGED", "STOCK_CHANGED", "IN_PROGRESS_CHANGED",
     "HARVEST_RESULT_CHANGED", "PROTOCOL_CHANGED", "PLAN_LATE",
     "MANUAL_REPLAN_AUTHORIZED"}
)
ALLOCATION_TYPES = frozenset({"DOMANDA", "STOCK", "PRODUZIONE_IN_CORSO", "RACCOLTA"})
ALLOCATION_STATES = frozenset({"ATTIVA", "CONSUMATA", "RILASCIATA", "SOSTITUITA", "INVALIDA"})
PLANNING_LINE_STATES = frozenset(
    {"PIANIFICATA", "PRONTA", "AVVIATA", "SODDISFATTA", "ANNULLATA", "SOSTITUITA", "TARDIVA"}
)
BUFFER_TYPES = frozenset({"NONE", "PERCENTAGE", "ABSOLUTE_SET"})
RUN_STATES = frozenset({"OPEN", "COMMITTED", "FAILED", "RECONCILIATION_REQUIRED"})
AUDIT_OPERATIONS = frozenset({"INSERT", "UPDATE", "DELETE", "STATE_TRANSITION", "CORRECTION"})
PROTOCOL_APPROVAL_STATES = frozenset({"BOZZA", "APPROVATA", "RITIRATA"})
PRODUCTION_PLANNING_PRIORITY_POLICY_V1 = "DELIVERY_THEN_PUBLIC_ID"
PRODUCTION_PLANNING_ALGORITHM_VERSION_V1 = "production-planning-v1"
HARVEST_TARGET_STRATEGY_V1 = "EARLIEST_APPROVED_WINDOW"


def _text(name: str, value: object, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidProductionPlanningModelError(f"{name} deve essere testo normalizzato non vuoto.")


def _instant(name: str, value: object) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise InvalidProductionPlanningModelError(f"{name} deve essere un istante timezone-aware.")


def _version(name: str, value: object, *, positive: bool = False) -> None:
    minimum = 1 if positive else 0
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise InvalidProductionPlanningModelError(f"{name} deve essere un intero >= {minimum}.")


def _decimal(name: str, value: object, *, positive: bool = False) -> Decimal:
    if isinstance(value, (float, bool)):
        raise InvalidProductionPlanningModelError(f"{name} non accetta float o booleani.")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)  # type: ignore[arg-type]
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidProductionPlanningModelError(f"{name} deve essere Decimal.") from exc
    if not parsed.is_finite() or parsed.as_tuple().exponent < -6:
        raise InvalidProductionPlanningModelError(f"{name} deve essere finito con massimo sei decimali.")
    if parsed < 0 or (positive and parsed <= 0):
        qualifier = "positivo" if positive else "non negativo"
        raise InvalidProductionPlanningModelError(f"{name} deve essere {qualifier}.")
    return parsed


@dataclass(frozen=True)
class PublicId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or re.fullmatch(r"[A-Z]+-[0-9]{6,}", self.value) is None:
            raise InvalidProductionPlanningModelError("Public ID non valido.")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class CanonicalHash:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or re.fullmatch(r"[0-9a-f]{64}", self.value) is None:
            raise InvalidProductionPlanningModelError("Hash canonico non valido.")


@dataclass(frozen=True)
class ExactQuantity:
    value: Decimal
    unit: UnitOfMeasure

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _decimal("quantity", self.value))
        if not isinstance(self.unit, UnitOfMeasure):
            raise InvalidProductionPlanningModelError("Unità di misura non valida.")


@dataclass(frozen=True)
class PlanningExecutionContext:
    actor: ActorId
    reason: str
    correlation_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidProductionPlanningModelError("actor non valido.")
        _text("reason", self.reason)
        _text("correlation_id", self.correlation_id)


@dataclass(frozen=True)
class PolicyVersionReference:
    policy_set_code: str
    version: int

    def __post_init__(self) -> None:
        _text("policy_set_code", self.policy_set_code)
        _version("policy_version", self.version, positive=True)


@dataclass(frozen=True)
class InitialProductionPlanningCommand:
    business_at: datetime
    policy: PolicyVersionReference
    context: PlanningExecutionContext

    def __post_init__(self) -> None:
        _instant("business_at", self.business_at)
        if not isinstance(self.policy, PolicyVersionReference) or not isinstance(
            self.context, PlanningExecutionContext
        ):
            raise InvalidProductionPlanningModelError("Policy o execution context non valido.")


@dataclass(frozen=True)
class ReplanProductionPlanningCommand(InitialProductionPlanningCommand):
    previous_revision_public_id: PublicId
    order_line_public_id: PublicId
    replanning_reason_code: str

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.previous_revision_public_id, PublicId) or not self.previous_revision_public_id.value.startswith("RVP-"):
            raise InvalidProductionPlanningModelError("previous_revision_public_id deve essere RVP-*.")
        if not isinstance(self.order_line_public_id, PublicId) or not self.order_line_public_id.value.startswith("RO-"):
            raise InvalidProductionPlanningModelError("order_line_public_id deve essere RO-*.")
        if self.replanning_reason_code not in REPLANNING_REASONS:
            raise InvalidProductionPlanningModelError("replanning_reason_code non congelato.")


ProductionPlanningCommand = InitialProductionPlanningCommand | ReplanProductionPlanningCommand


@dataclass(frozen=True)
class DemandSnapshot:
    order_public_id: PublicId
    order_line_public_id: PublicId
    order_version: int
    order_line_version: int
    order_state: OrdineState
    variety_public_id: PublicId
    ordered: ExactQuantity
    delivered: ExactQuantity
    commercial_residual: ExactQuantity
    order_date: date
    delivery_date: date
    commercial_priority: int | None
    provenance: str

    def __post_init__(self) -> None:
        for name, value in (("order_version", self.order_version), ("order_line_version", self.order_line_version)):
            _version(name, value)
        if self.order_state not in (OrdineState.APERTO, OrdineState.PARZIALMENTE_EVASO):
            raise InvalidProductionPlanningModelError("ORDINE non eleggibile.")
        if not all(isinstance(item, ExactQuantity) for item in (self.ordered, self.delivered, self.commercial_residual)):
            raise InvalidProductionPlanningModelError("Quantità domanda non valide.")
        if len({self.ordered.unit, self.delivered.unit, self.commercial_residual.unit}) != 1:
            raise InvalidProductionPlanningModelError("UOM domanda incoerenti.")
        if self.ordered.value <= 0 or self.delivered.value + self.commercial_residual.value != self.ordered.value or self.commercial_residual.value <= 0:
            raise InvalidProductionPlanningModelError("Residuo commerciale incoerente.")
        if not isinstance(self.order_date, date) or not isinstance(self.delivery_date, date):
            raise InvalidProductionPlanningModelError("Date domanda non valide.")
        _text("provenance", self.provenance)


@dataclass(frozen=True)
class ProductionKnowledgeSnapshot:
    protocol_version_public_id: PublicId
    protocol_version_number: int
    approval_state: str
    variety_public_id: PublicId
    cultivar_reference: str
    productive_use_reference: str
    valid_from: date
    valid_to: date | None
    hydration_hours: Decimal
    planned_sowing_time: time
    target_harvest_time: time
    germination_days: int
    light_growth_days: int
    seed_grams_per_set: Decimal
    expected_yield: ExactQuantity
    production_granularity: Decimal
    harvest_min_lead_days: int
    harvest_max_lead_days: int
    temporal_buffer_minutes: int
    provenance: str

    def __post_init__(self) -> None:
        _version("protocol_version_number", self.protocol_version_number, positive=True)
        if self.approval_state not in PROTOCOL_APPROVAL_STATES:
            raise InvalidProductionPlanningModelError(
                "Stato approvazione protocollo non congelato."
            )
        for name in ("cultivar_reference", "productive_use_reference", "provenance"):
            _text(name, getattr(self, name))
        object.__setattr__(self, "hydration_hours", _decimal("hydration_hours", self.hydration_hours))
        object.__setattr__(self, "seed_grams_per_set", _decimal("seed_grams_per_set", self.seed_grams_per_set, positive=True))
        object.__setattr__(self, "production_granularity", _decimal("production_granularity", self.production_granularity, positive=True))
        for name in ("germination_days", "light_growth_days", "temporal_buffer_minutes"):
            _version(name, getattr(self, name))
        _version("harvest_min_lead_days", self.harvest_min_lead_days, positive=True)
        if self.harvest_max_lead_days < self.harvest_min_lead_days:
            raise InvalidProductionPlanningModelError("Harvest window incoerente.")
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise InvalidProductionPlanningModelError("Validità protocollo incoerente.")


@dataclass(frozen=True)
class PlanningPolicySnapshot:
    reference: PolicyVersionReference
    valid_from: date
    valid_to: date | None
    quantitative_buffer_type: str
    quantitative_buffer_value: Decimal | None
    priority_policy_code: str
    algorithm_version: str
    harvest_target_strategy: str

    def __post_init__(self) -> None:
        if self.quantitative_buffer_type not in BUFFER_TYPES:
            raise InvalidProductionPlanningModelError("Policy Planning non valida.")
        if self.quantitative_buffer_type == "NONE":
            if self.quantitative_buffer_value is not None:
                raise InvalidProductionPlanningModelError("NONE vieta un valore buffer.")
        elif self.quantitative_buffer_value is None:
            raise InvalidProductionPlanningModelError("Policy buffer richiede un valore.")
        else:
            object.__setattr__(self, "quantitative_buffer_value", _decimal("buffer", self.quantitative_buffer_value))
        if self.priority_policy_code != PRODUCTION_PLANNING_PRIORITY_POLICY_V1:
            raise InvalidProductionPlanningModelError("Priority policy V1 non supportata.")
        if self.algorithm_version != PRODUCTION_PLANNING_ALGORITHM_VERSION_V1:
            raise InvalidProductionPlanningModelError("Planning algorithm version V1 non supportata.")
        if self.harvest_target_strategy != HARVEST_TARGET_STRATEGY_V1:
            raise InvalidProductionPlanningModelError("Harvest target strategy V1 non supportata.")


@dataclass(frozen=True)
class StockResourceSnapshot:
    resource_public_id: PublicId
    variety_public_id: PublicId
    eligible: ExactQuantity
    allocated: ExactQuantity
    allocable_residual: ExactQuantity
    version: int
    readiness_code: str

    def __post_init__(self) -> None:
        _resource_quantities(self.eligible, self.allocated, self.allocable_residual)
        _version("stock version", self.version)
        _text("readiness_code", self.readiness_code)


@dataclass(frozen=True)
class InProgressResourceSnapshot:
    semina_public_id: PublicId
    variety_public_id: PublicId
    protocol_version_public_id: PublicId
    expected_useful: ExactQuantity
    allocated: ExactQuantity
    allocable_residual: ExactQuantity
    harvest_window_start: datetime
    harvest_window_end: datetime
    state: SeminaState
    version: int

    def __post_init__(self) -> None:
        _resource_quantities(self.expected_useful, self.allocated, self.allocable_residual)
        _instant("harvest_window_start", self.harvest_window_start)
        _instant("harvest_window_end", self.harvest_window_end)
        if self.harvest_window_end <= self.harvest_window_start:
            raise InvalidProductionPlanningModelError("Finestra SEMINA incoerente.")
        _version("semina version", self.version)


@dataclass(frozen=True)
class HarvestResourceSnapshot:
    harvest_public_id: PublicId
    semina_public_id: PublicId
    variety_public_id: PublicId
    eligible: ExactQuantity
    allocated: ExactQuantity
    allocable_residual: ExactQuantity
    harvested_at: datetime
    provenance: str

    def __post_init__(self) -> None:
        _resource_quantities(self.eligible, self.allocated, self.allocable_residual)
        _instant("harvested_at", self.harvested_at)
        _text("provenance", self.provenance)


@dataclass(frozen=True)
class ActiveAllocationSnapshot:
    allocation_public_id: PublicId
    allocation_type: str
    source_public_id: PublicId
    destination_order_line_public_id: PublicId
    allocated_quantity: ExactQuantity
    consumed_quantity: ExactQuantity
    released_quantity: ExactQuantity
    transferred_quantity: ExactQuantity
    invalidated_quantity: ExactQuantity
    remaining_quantity: ExactQuantity
    state: str
    version: int

    def __post_init__(self) -> None:
        if self.allocation_type not in ALLOCATION_TYPES or self.state not in ALLOCATION_STATES:
            raise InvalidProductionPlanningModelError("Allocazione snapshot non valida.")
        quantities = (
            self.allocated_quantity,
            self.consumed_quantity,
            self.released_quantity,
            self.transferred_quantity,
            self.invalidated_quantity,
            self.remaining_quantity,
        )
        if not all(isinstance(item, ExactQuantity) for item in quantities):
            raise InvalidProductionPlanningModelError("Saldi allocazione snapshot non validi.")
        if len({item.unit for item in quantities}) != 1:
            raise InvalidProductionPlanningModelError("UOM saldi allocazione snapshot incoerenti.")
        if self.allocated_quantity.value <= 0 or self.remaining_quantity.value != (
            self.allocated_quantity.value
            - self.consumed_quantity.value
            - self.released_quantity.value
            - self.transferred_quantity.value
            - self.invalidated_quantity.value
        ):
            raise InvalidProductionPlanningModelError("Saldi allocazione snapshot incoerenti.")
        _version("allocation version", self.version)


@dataclass(frozen=True)
class CurrentPlanSnapshot:
    plan_public_id: PublicId
    plan_version: int
    current_revision_public_id: PublicId
    current_revision_version: int
    revision_number: int

    def __post_init__(self) -> None:
        _version("plan_version", self.plan_version)
        _version("current_revision_version", self.current_revision_version)
        _version("revision_number", self.revision_number, positive=True)


@dataclass(frozen=True)
class CurrentPlanningLineSnapshot:
    planning_line_public_id: PublicId
    revision_public_id: PublicId
    order_line_public_id: PublicId
    state: str
    version: int

    def __post_init__(self) -> None:
        if self.state not in PLANNING_LINE_STATES:
            raise InvalidProductionPlanningModelError("Stato riga Planning corrente non congelato.")
        _version("planning line version", self.version)


@dataclass(frozen=True)
class PlanningInputSnapshot:
    business_at: datetime
    policy: PlanningPolicySnapshot
    demands: tuple[DemandSnapshot, ...]
    knowledge: tuple[ProductionKnowledgeSnapshot, ...]
    stock: tuple[StockResourceSnapshot, ...]
    in_progress: tuple[InProgressResourceSnapshot, ...]
    harvests: tuple[HarvestResourceSnapshot, ...]
    allocations: tuple[ActiveAllocationSnapshot, ...]
    current_plans: tuple[CurrentPlanSnapshot, ...]
    current_planning_lines: tuple[CurrentPlanningLineSnapshot, ...]

    def __post_init__(self) -> None:
        _instant("business_at", self.business_at)
        for name in ("demands", "knowledge", "stock", "in_progress", "harvests", "allocations", "current_plans", "current_planning_lines"):
            if not isinstance(getattr(self, name), tuple):
                raise InvalidProductionPlanningModelError(f"{name} deve essere una tuple ordinata.")
        _unique_sorted(self.demands, lambda item: item.order_line_public_id.value, "demands")
        _unique_sorted(self.stock, lambda item: item.resource_public_id.value, "stock")
        _unique_sorted(self.in_progress, lambda item: item.semina_public_id.value, "in_progress")
        _unique_sorted(self.harvests, lambda item: item.harvest_public_id.value, "harvests")
        _unique_sorted(self.allocations, lambda item: item.allocation_public_id.value, "allocations")
        _unique_sorted(self.current_planning_lines, lambda item: item.planning_line_public_id.value, "current_planning_lines")


@dataclass(frozen=True)
class CanonicalPlanningRequest:
    order_line_public_id: PublicId
    commercial_residual: ExactQuantity
    delivery_date: date
    protocol_version_public_id: PublicId
    policy: PolicyVersionReference
    planning_key_v1: CanonicalHash


@dataclass(frozen=True)
class CanonicalReplanningSnapshot:
    previous_revision_public_id: PublicId
    previous_plan_revision_version: int
    order_line_public_id: PublicId
    order_public_id: PublicId
    order_state: OrdineState
    order_version: int
    order_line_version: int
    ordered_quantity: ExactQuantity
    delivered_quantity: ExactQuantity
    commercial_residual_quantity: ExactQuantity
    delivery_date: date
    variety_public_id: PublicId
    protocol_version_public_id: PublicId
    protocol_version_number: int
    protocol_valid_from: date
    protocol_valid_to: date | None
    reason_code: str
    policy: PolicyVersionReference
    quantitative_buffer_type: str
    quantitative_buffer_value: Decimal | None
    temporal_buffer_minutes: int
    production_granularity: Decimal
    stock: tuple[StockResourceSnapshot, ...]
    in_progress: tuple[InProgressResourceSnapshot, ...]
    allocations: tuple[ActiveAllocationSnapshot, ...]
    canonical_text: str
    canonical_snapshot_hash: CanonicalHash
    replanning_key_v1: CanonicalHash

    def __post_init__(self) -> None:
        if self.reason_code not in REPLANNING_REASONS:
            raise InvalidProductionPlanningModelError("Reason replanning non congelata.")
        for name, value in (
            ("previous_plan_revision_version", self.previous_plan_revision_version),
            ("order_version", self.order_version),
            ("order_line_version", self.order_line_version),
        ):
            _version(name, value)
        _version("protocol_version_number", self.protocol_version_number, positive=True)
        _version("temporal_buffer_minutes", self.temporal_buffer_minutes)
        if self.order_state not in (OrdineState.APERTO, OrdineState.PARZIALMENTE_EVASO):
            raise InvalidProductionPlanningModelError("Stato ORDINE replanning non eleggibile.")
        quantities = (self.ordered_quantity, self.delivered_quantity, self.commercial_residual_quantity)
        if len({item.unit for item in quantities}) != 1 or self.delivered_quantity.value + self.commercial_residual_quantity.value != self.ordered_quantity.value:
            raise InvalidProductionPlanningModelError("Quantita replanning incoerenti.")
        if self.protocol_valid_to is not None and self.protocol_valid_to <= self.protocol_valid_from:
            raise InvalidProductionPlanningModelError("Validita protocollo replanning incoerente.")
        if self.quantitative_buffer_type not in BUFFER_TYPES:
            raise InvalidProductionPlanningModelError("Buffer replanning non congelato.")
        if (self.quantitative_buffer_type == "NONE") != (self.quantitative_buffer_value is None):
            raise InvalidProductionPlanningModelError("Valore buffer replanning incoerente.")
        if self.quantitative_buffer_value is not None:
            object.__setattr__(self, "quantitative_buffer_value", _decimal("quantitative_buffer_value", self.quantitative_buffer_value))
        object.__setattr__(self, "production_granularity", _decimal("production_granularity", self.production_granularity, positive=True))
        _text("canonical_text", self.canonical_text)
        calculated_hash = hashlib.sha256(self.canonical_text.encode("utf-8")).hexdigest()
        if self.canonical_snapshot_hash.value != calculated_hash:
            raise InvalidProductionPlanningModelError("canonical_text e canonical_hash non coincidono.")
        _unique_sorted(self.stock, lambda item: item.resource_public_id.value, "stock")
        _unique_sorted(self.in_progress, lambda item: item.semina_public_id.value, "in_progress")
        _unique_sorted(self.allocations, lambda item: item.allocation_public_id.value, "allocations")


@dataclass(frozen=True)
class PlanningCandidate:
    demand: DemandSnapshot
    knowledge: ProductionKnowledgeSnapshot
    harvest_target_at: datetime
    sowing_at: datetime
    light_at: datetime
    hydration_at: datetime
    productive_quantity: ExactQuantity
    provenance: str

    def __post_init__(self) -> None:
        for name in ("harvest_target_at", "sowing_at", "light_at", "hydration_at"):
            _instant(name, getattr(self, name))
        if not self.hydration_at <= self.sowing_at <= self.light_at <= self.harvest_target_at:
            raise InvalidProductionPlanningModelError("Timeline di backplanning incoerente.")
        _text("provenance", self.provenance)


@dataclass(frozen=True)
class PlanningLineDraft:
    public_id: PublicId
    candidate: PlanningCandidate
    state: str
    planning_key: CanonicalHash
    expected_order_version: int
    expected_order_line_version: int
    stock_coverage: ExactQuantity
    in_progress_coverage: ExactQuantity
    allocated_harvest_coverage: ExactQuantity
    production_deficit: ExactQuantity
    quantitative_buffer_type: str
    quantitative_buffer_value: Decimal | None
    calculated_quantitative_buffer: Decimal
    pre_granularity_quantity: Decimal
    authorized_productive_quantity: ExactQuantity
    remaining_to_start: ExactQuantity
    harvest_window_start: date
    harvest_window_end: date

    def __post_init__(self) -> None:
        if self.state not in PLANNING_LINE_STATES:
            raise InvalidProductionPlanningModelError("Stato riga piano non congelato.")
        _version("expected_order_version", self.expected_order_version)
        _version("expected_order_line_version", self.expected_order_line_version)
        quantities = (
            self.candidate.demand.commercial_residual,
            self.stock_coverage,
            self.in_progress_coverage,
            self.allocated_harvest_coverage,
            self.production_deficit,
            self.authorized_productive_quantity,
            self.remaining_to_start,
        )
        if len({item.unit for item in quantities}) != 1:
            raise InvalidProductionPlanningModelError("UOM riga piano incoerenti.")
        covered = self.stock_coverage.value + self.in_progress_coverage.value + self.allocated_harvest_coverage.value
        if covered + self.production_deficit.value != self.candidate.demand.commercial_residual.value:
            raise InvalidProductionPlanningModelError("Coperture e deficit non bilanciano la domanda residua.")
        if self.authorized_productive_quantity != self.candidate.productive_quantity or self.remaining_to_start != self.authorized_productive_quantity:
            raise InvalidProductionPlanningModelError("Quantita produttiva draft incoerente.")
        if self.quantitative_buffer_type not in BUFFER_TYPES:
            raise InvalidProductionPlanningModelError("Buffer riga piano non congelato.")
        if (self.quantitative_buffer_type == "NONE") != (self.quantitative_buffer_value is None):
            raise InvalidProductionPlanningModelError("Valore buffer riga piano incoerente.")
        for name in ("quantitative_buffer_value", "calculated_quantitative_buffer", "pre_granularity_quantity"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _decimal(name, value))
        if self.harvest_window_end < self.harvest_window_start:
            raise InvalidProductionPlanningModelError("Finestra raccolta riga piano incoerente.")


@dataclass(frozen=True)
class SeedResourceDraft:
    planning_line_public_id: PublicId
    required_grams: Decimal
    grams_per_set: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_grams", _decimal("required_grams", self.required_grams, positive=True))
        object.__setattr__(self, "grams_per_set", _decimal("grams_per_set", self.grams_per_set, positive=True))


@dataclass(frozen=True)
class AllocationDraft:
    public_id: PublicId
    allocation_type: str
    planning_line_public_id: PublicId
    source_public_id: PublicId
    destination_order_line_public_id: PublicId
    quantity: ExactQuantity
    state: str = "ATTIVA"

    def __post_init__(self) -> None:
        if self.allocation_type not in ALLOCATION_TYPES or self.state != "ATTIVA":
            raise InvalidProductionPlanningModelError("Nuova allocazione deve avere tipo congelato e stato ATTIVA.")
        if self.quantity.value <= 0:
            raise InvalidProductionPlanningModelError("Allocazione deve essere positiva.")


@dataclass(frozen=True)
class AllocationTransitionDraft:
    allocation_public_id: PublicId
    expected_version: int
    current_state: str
    target_state: str
    observed_allocated_quantity: Decimal
    observed_consumed_quantity: Decimal
    observed_released_quantity: Decimal
    observed_transferred_quantity: Decimal
    observed_invalidated_quantity: Decimal
    observed_remaining_quantity: Decimal
    consumed_quantity_delta: Decimal
    released_quantity_delta: Decimal
    transferred_quantity_delta: Decimal
    invalidated_quantity_delta: Decimal
    replacement_allocation_public_id: PublicId | None
    reason: str
    provenance: str

    def __post_init__(self) -> None:
        _version("expected_version", self.expected_version)
        if self.current_state != "ATTIVA" or self.target_state not in ALLOCATION_STATES:
            raise InvalidProductionPlanningModelError("Stato transizione allocazione non valido.")
        observed_names = (
            "observed_allocated_quantity",
            "observed_consumed_quantity",
            "observed_released_quantity",
            "observed_transferred_quantity",
            "observed_invalidated_quantity",
            "observed_remaining_quantity",
        )
        delta_names = (
            "consumed_quantity_delta",
            "released_quantity_delta",
            "transferred_quantity_delta",
            "invalidated_quantity_delta",
        )
        for name in observed_names + delta_names:
            object.__setattr__(self, name, _decimal(name, getattr(self, name)))
        if self.observed_allocated_quantity <= 0:
            raise InvalidProductionPlanningModelError("Quantità allocata observed deve essere positiva.")
        expected_observed_remaining = (
            self.observed_allocated_quantity
            - self.observed_consumed_quantity
            - self.observed_released_quantity
            - self.observed_transferred_quantity
            - self.observed_invalidated_quantity
        )
        if self.observed_remaining_quantity != expected_observed_remaining:
            raise InvalidProductionPlanningModelError("Saldi observed allocazione incoerenti.")
        deltas = (
            self.consumed_quantity_delta,
            self.released_quantity_delta,
            self.transferred_quantity_delta,
            self.invalidated_quantity_delta,
        )
        if not any(value > 0 for value in deltas):
            raise InvalidProductionPlanningModelError("La transizione richiede almeno un delta positivo.")
        disposition_deltas = (
            self.released_quantity_delta,
            self.transferred_quantity_delta,
            self.invalidated_quantity_delta,
        )
        if sum(value > 0 for value in disposition_deltas) > 1:
            raise InvalidProductionPlanningModelError("Disposizioni allocation mutuamente esclusive.")
        if sum(deltas) > self.observed_remaining_quantity:
            raise InvalidProductionPlanningModelError("Delta oltre il residuo observed.")
        has_replacement = self.replacement_allocation_public_id is not None
        if (self.transferred_quantity_delta > 0) != has_replacement:
            raise InvalidProductionPlanningModelError("Replacement incoerente con il transfer.")
        expected_remaining_after = self.observed_remaining_quantity - sum(deltas)
        if expected_remaining_after > 0:
            expected_target = "ATTIVA"
        elif self.released_quantity_delta > 0:
            expected_target = "RILASCIATA"
        elif self.transferred_quantity_delta > 0:
            expected_target = "SOSTITUITA"
        elif self.invalidated_quantity_delta > 0:
            expected_target = "INVALIDA"
        elif self.observed_consumed_quantity + self.consumed_quantity_delta == self.observed_allocated_quantity:
            expected_target = "CONSUMATA"
        else:
            raise InvalidProductionPlanningModelError("Conclusione quantitativa senza stato terminale coerente.")
        if self.target_state != expected_target:
            raise InvalidProductionPlanningModelError("target_state incoerente con i saldi risultanti.")
        _text("reason", self.reason)
        _text("provenance", self.provenance)

    @property
    def expected_remaining_after(self) -> Decimal:
        return self.observed_remaining_quantity - (
            self.consumed_quantity_delta
            + self.released_quantity_delta
            + self.transferred_quantity_delta
            + self.invalidated_quantity_delta
        )


@dataclass(frozen=True)
class PlanRevisionDraft:
    plan_public_id: PublicId
    revision_public_id: PublicId
    revision_number: int
    request_key: CanonicalHash
    lines: tuple[PlanningLineDraft, ...]
    plan_state: str
    expected_plan_version: int | None = None
    expected_current_revision_version: int | None = None
    previous_revision_public_id: PublicId | None = None
    replanning_reason_code: str | None = None
    canonical_replanning_snapshot: CanonicalReplanningSnapshot | None = None

    def __post_init__(self) -> None:
        _version("revision_number", self.revision_number, positive=True)
        _text("plan_state", self.plan_state)
        if self.expected_plan_version is not None:
            _version("expected_plan_version", self.expected_plan_version)
        if self.expected_current_revision_version is not None:
            _version("expected_current_revision_version", self.expected_current_revision_version)
        if not isinstance(self.lines, tuple) or not self.lines:
            raise InvalidProductionPlanningModelError("Una revisione completa richiede righe.")
        is_initial = self.revision_number == 1
        extras = (self.previous_revision_public_id, self.replanning_reason_code, self.canonical_replanning_snapshot)
        if is_initial and any(item is not None for item in extras):
            raise InvalidProductionPlanningModelError("La prima revisione vieta dati replanning.")
        if not is_initial and any(item is None for item in extras):
            raise InvalidProductionPlanningModelError("Il replanning richiede precedente, reason e snapshot.")
        if is_initial and (self.expected_plan_version is not None or self.expected_current_revision_version is not None):
            raise InvalidProductionPlanningModelError("La prima revisione non possiede versioni correnti attese.")
        if not is_initial and (self.expected_plan_version is None or self.expected_current_revision_version is None):
            raise InvalidProductionPlanningModelError("Il replanning richiede le versioni correnti attese.")


@dataclass(frozen=True)
class ProductionPlanningRunCounters:
    orders_read: int
    order_lines_evaluated: int
    lines_fully_covered: int
    lines_partially_covered: int
    planning_lines_generated: int
    allocations_generated: int
    late_lines: int
    non_producible_lines: int
    skipped_items: int

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            _version(name, value)


@dataclass(frozen=True)
class AuditDraft:
    entity_type: str
    entity_public_id: PublicId
    operation: str
    before_payload: tuple[tuple[str, str], ...]
    after_payload: tuple[tuple[str, str], ...]
    provenance: str

    def __post_init__(self) -> None:
        _text("entity_type", self.entity_type)
        if self.operation not in AUDIT_OPERATIONS:
            raise InvalidProductionPlanningModelError("Operazione audit non congelata.")
        if not self.before_payload and not self.after_payload:
            raise InvalidProductionPlanningModelError("Audit privo di payload.")
        if self.operation == "INSERT" and not self.after_payload:
            raise InvalidProductionPlanningModelError("Audit INSERT richiede after payload.")
        if self.operation == "DELETE" and not self.before_payload:
            raise InvalidProductionPlanningModelError("Audit DELETE richiede before payload.")
        _text("provenance", self.provenance)
        for name, payload in (("before_payload", self.before_payload), ("after_payload", self.after_payload)):
            if not isinstance(payload, tuple):
                raise InvalidProductionPlanningModelError(f"{name} deve essere una tuple canonica.")
            keys = tuple(key for key, _ in payload)
            if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
                raise InvalidProductionPlanningModelError(f"{name} deve essere unico e ordinato.")
            for key, value in payload:
                _text(f"{name}.key", key)
                if not isinstance(value, str):
                    raise InvalidProductionPlanningModelError(f"{name} contiene un valore non canonico.")


@dataclass(frozen=True)
class RunMessage:
    position: int
    message_type: str
    code: str
    message: str
    created_at: datetime
    failure_category: str | None = None

    def __post_init__(self) -> None:
        _version("position", self.position, positive=True)
        if self.message_type not in {"WARNING", "ERROR"}:
            raise InvalidProductionPlanningModelError("Tipo messaggio non congelato.")
        if (self.message_type == "ERROR") != (self.failure_category is not None):
            raise InvalidProductionPlanningModelError("Categoria obbligatoria esclusivamente per ERROR.")
        if self.failure_category is not None and self.failure_category not in FROZEN_FAILURE_CATEGORIES:
            raise InvalidProductionPlanningModelError("Failure category non congelata.")
        _text("code", self.code)
        _text("message", self.message)
        _instant("created_at", self.created_at)


@dataclass(frozen=True)
class ProductionPlanningRunSnapshot:
    public_id: PublicId
    expected_version: int
    state: str

    def __post_init__(self) -> None:
        _version("run expected_version", self.expected_version)
        if self.state not in RUN_STATES:
            raise InvalidProductionPlanningModelError("Stato RUN non congelato.")


@dataclass(frozen=True)
class ProductionPlanningCommit:
    run: ProductionPlanningRunSnapshot
    policy: PolicyVersionReference
    business_at: datetime
    context: PlanningExecutionContext
    revisions: tuple[PlanRevisionDraft, ...]
    seed_resources: tuple[SeedResourceDraft, ...]
    allocations: tuple[AllocationDraft, ...]
    allocation_transitions: tuple[AllocationTransitionDraft, ...]
    messages: tuple[RunMessage, ...]
    counters: ProductionPlanningRunCounters
    audits: tuple[AuditDraft, ...]
    input_snapshot: PlanningInputSnapshot

    def __post_init__(self) -> None:
        _instant("business_at", self.business_at)
        if not self.revisions:
            raise InvalidProductionPlanningModelError("Write set privo di revisioni.")
        _unique_sorted(self.revisions, lambda item: item.plan_public_id.value, "revisions")
        _unique_sorted(self.allocations, lambda item: item.public_id.value, "allocations")
        if not isinstance(self.allocation_transitions, tuple):
            raise InvalidProductionPlanningModelError("allocation_transitions deve essere una tuple ordinata.")
        _unique_sorted(
            self.allocation_transitions,
            lambda item: item.allocation_public_id.value,
            "allocation_transitions",
        )
        if not isinstance(self.counters, ProductionPlanningRunCounters):
            raise InvalidProductionPlanningModelError("Contatori RUN mancanti.")
        if not isinstance(self.audits, tuple) or not self.audits:
            raise InvalidProductionPlanningModelError("Audit write set mancante.")
        if self.business_at != self.input_snapshot.business_at or self.policy != self.input_snapshot.policy.reference:
            raise InvalidProductionPlanningModelError("Scope commit non coerente con lo snapshot.")
        generated_lines = sum(len(revision.lines) for revision in self.revisions)
        if self.counters.planning_lines_generated != generated_lines or self.counters.allocations_generated != len(self.allocations):
            raise InvalidProductionPlanningModelError("Contatori RUN non coerenti con il write set.")
        audit_keys = tuple((item.entity_type, item.entity_public_id.value, item.operation) for item in self.audits)
        if audit_keys != tuple(sorted(audit_keys)) or len(audit_keys) != len(set(audit_keys)):
            raise InvalidProductionPlanningModelError("Audit devono essere unici e ordinati deterministicamente.")
        if tuple(message.position for message in self.messages) != tuple(range(1, len(self.messages) + 1)):
            raise InvalidProductionPlanningModelError("Messaggi non densamente ordinati.")


@dataclass(frozen=True)
class RevisionCommitResult:
    plan_public_id: PublicId
    revision_public_id: PublicId
    revision_request_key: CanonicalHash
    planning_key_v1: CanonicalHash | None
    replanning_key_v1: CanonicalHash | None
    reused_existing_revision: bool

    def __post_init__(self) -> None:
        keys = tuple(
            key for key in (self.planning_key_v1, self.replanning_key_v1) if key is not None
        )
        if len(keys) != 1:
            raise InvalidProductionPlanningModelError(
                "Il risultato revisione richiede esattamente una chiave initial o replanning."
            )
        if self.revision_request_key != keys[0]:
            raise InvalidProductionPlanningModelError(
                "revision_request_key non coincide con la chiave strutturale della revisione."
            )
        if not isinstance(self.reused_existing_revision, bool):
            raise InvalidProductionPlanningModelError("Indicatore replay revisione non valido.")


@dataclass(frozen=True)
class ProductionPlanningResult:
    planning_run_public_id: PublicId
    run_state: str
    plan_public_ids: tuple[PublicId, ...]
    current_revision_public_ids: tuple[PublicId, ...]
    revision_results: tuple[RevisionCommitResult, ...]
    planning_line_public_ids: tuple[PublicId, ...]
    allocation_public_ids: tuple[PublicId, ...]
    committed_at: datetime
    warnings: tuple[RunMessage, ...]

    def __post_init__(self) -> None:
        if self.run_state not in {"COMMITTED", "RECONCILIATION_REQUIRED"}:
            raise InvalidProductionPlanningModelError("Result state non valido.")
        _instant("committed_at", self.committed_at)
        if not isinstance(self.revision_results, tuple) or not self.revision_results:
            raise InvalidProductionPlanningModelError("Result privo di revisioni committed.")
        revision_keys = tuple(
            (item.plan_public_id.value, item.revision_public_id.value)
            for item in self.revision_results
        )
        if revision_keys != tuple(sorted(revision_keys)) or len(revision_keys) != len(set(revision_keys)):
            raise InvalidProductionPlanningModelError(
                "Risultati revisione devono essere unici e ordinati deterministicamente."
            )
        if self.plan_public_ids != tuple(item.plan_public_id for item in self.revision_results):
            raise InvalidProductionPlanningModelError("Piani non allineati ai risultati revisione.")
        if self.current_revision_public_ids != tuple(
            item.revision_public_id for item in self.revision_results
        ):
            raise InvalidProductionPlanningModelError("Piani e revisioni correnti non allineati.")


def _resource_quantities(total: ExactQuantity, allocated: ExactQuantity, residual: ExactQuantity) -> None:
    if not all(isinstance(item, ExactQuantity) for item in (total, allocated, residual)):
        raise InvalidProductionPlanningModelError("Resource quantity non valida.")
    if len({total.unit, allocated.unit, residual.unit}) != 1 or allocated.value + residual.value != total.value:
        raise InvalidProductionPlanningModelError("Resource quantities incoerenti.")


def _unique_sorted(items: tuple[object, ...], key, name: str) -> None:
    keys = tuple(key(item) for item in items)
    if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
        raise InvalidProductionPlanningModelError(f"{name} deve essere unico e ordinato deterministicamente.")
