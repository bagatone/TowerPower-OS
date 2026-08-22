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
ALLOCATION_DISPOSITION_CAUSES = frozenset(
    {
        "DEMAND_REDUCED",
        "DEMAND_CANCELLED",
        "DEMAND_COVERED_ELSEWHERE",
        "REALLOCATION_REQUIRED",
        "REVISION_REPLACEMENT",
        "SOURCE_UNUSABLE",
        "SEEDING_FAILED",
        "HARVEST_UNAVAILABLE",
        "STOCK_QUANTITY_INVALIDATED",
        "DATA_CORRUPTION_CONFIRMED",
        "MANUAL_INVALIDATION_AUTHORIZED",
    }
)
ALLOCATION_SOURCE_USABILITY = frozenset(
    {"REUSABLE", "TRANSFERABLE_ONLY", "UNUSABLE"}
)
ALLOCATION_DISPOSITIONS = frozenset({"RILASCIATA", "SOSTITUITA", "INVALIDA"})
_RELEASE_CAUSES = frozenset(
    {"DEMAND_REDUCED", "DEMAND_CANCELLED", "DEMAND_COVERED_ELSEWHERE"}
)
_TRANSFER_CAUSES = frozenset({"REALLOCATION_REQUIRED", "REVISION_REPLACEMENT"})
_INVALIDATION_CAUSES = frozenset(
    {
        "SOURCE_UNUSABLE",
        "SEEDING_FAILED",
        "HARVEST_UNAVAILABLE",
        "STOCK_QUANTITY_INVALIDATED",
        "DATA_CORRUPTION_CONFIRMED",
        "MANUAL_INVALIDATION_AUTHORIZED",
    }
)
PRODUCTION_PLANNING_PRIORITY_POLICY_V1 = "DELIVERY_THEN_PUBLIC_ID"
PRODUCTION_PLANNING_ALGORITHM_VERSION_V1 = "production-planning-v1"
HARVEST_TARGET_STRATEGY_V1 = "EARLIEST_APPROVED_WINDOW"
PLANNING_LINE_SLOT_MARKER_V1 = "PRODUCTION-PLANNING-LINE-SLOT-V1"
REPLACEMENT_ALLOCATION_SLOT_MARKER_V1 = (
    "PRODUCTION-REPLACEMENT-ALLOCATION-SLOT-V1"
)
DISPOSITION_SET_MARKER_V1 = "PRODUCTION-REPLANNING-DISPOSITION-SET-V1"


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


def canonical_frame(value: str | None) -> str:
    if value is None:
        return "-1:"
    if not isinstance(value, str):
        raise InvalidProductionPlanningModelError("Canonical frame richiede testo o NULL.")
    return f"{len(value.encode('utf-8'))}:{value}"


def canonical_record(*values: str | None) -> str:
    return "".join(canonical_frame(value) for value in values)


def canonical_list(values: tuple[str, ...]) -> str:
    return f"{len(values)};" + "".join(canonical_frame(value) for value in values)


def parse_canonical_slot_key(
    value: str, *, marker: str, field_count: int,
) -> tuple[str, ...]:
    if not isinstance(value, str) or not value:
        raise InvalidProductionPlanningModelError("Canonical slot key non valida.")
    fields: list[str] = []
    offset = 0
    raw = value.encode("utf-8")
    while offset < len(raw):
        colon = raw.find(b":", offset)
        if colon < 0:
            raise InvalidProductionPlanningModelError("Canonical slot framing non valido.")
        length_text = raw[offset:colon]
        if not length_text or not length_text.isdigit() or (
            len(length_text) > 1 and length_text.startswith(b"0")
        ):
            raise InvalidProductionPlanningModelError("Canonical slot length non valida.")
        length = int(length_text)
        start = colon + 1
        end = start + length
        if end > len(raw):
            raise InvalidProductionPlanningModelError("Canonical slot field troncato.")
        try:
            fields.append(raw[start:end].decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise InvalidProductionPlanningModelError("Canonical slot UTF-8 non valido.") from exc
        offset = end
    result = tuple(fields)
    if len(result) != field_count or result[0] != marker or canonical_record(*result) != value:
        raise InvalidProductionPlanningModelError("Canonical slot key non canonica.")
    if any(not field or field != field.strip() for field in result):
        raise InvalidProductionPlanningModelError("Canonical slot field non normalizzato.")
    return result


def planning_line_slot_key_v1(
    previous_plan_revision_public_id: PublicId,
    destination_order_line_public_id: PublicId,
) -> str:
    if not isinstance(previous_plan_revision_public_id, PublicId) or not isinstance(
        destination_order_line_public_id, PublicId
    ):
        raise InvalidProductionPlanningModelError("Planning-line slot identity non valida.")
    return canonical_record(
        PLANNING_LINE_SLOT_MARKER_V1,
        previous_plan_revision_public_id.value,
        destination_order_line_public_id.value,
    )


def replacement_allocation_slot_key_v1(
    parent_allocation_public_id: PublicId,
    replacement_allocation_type: str,
    replacement_source_public_id: PublicId,
    destination_order_line_public_id: PublicId,
    destination_planning_line_slot_key: str,
) -> str:
    if not all(isinstance(item, PublicId) for item in (
        parent_allocation_public_id, replacement_source_public_id,
        destination_order_line_public_id,
    )) or replacement_allocation_type not in ALLOCATION_TYPES:
        raise InvalidProductionPlanningModelError("Replacement slot identity non valida.")
    parse_canonical_slot_key(
        destination_planning_line_slot_key,
        marker=PLANNING_LINE_SLOT_MARKER_V1, field_count=3,
    )
    return canonical_record(
        REPLACEMENT_ALLOCATION_SLOT_MARKER_V1,
        parent_allocation_public_id.value,
        replacement_allocation_type,
        replacement_source_public_id.value,
        destination_order_line_public_id.value,
        destination_planning_line_slot_key,
    )


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
class ProductionPlanningIdentitySlot:
    sequence_name: str
    slot_kind: str
    canonical_slot_key: str
    position: int

    def __post_init__(self) -> None:
        for name in ("sequence_name", "slot_kind", "canonical_slot_key"):
            _text(name, getattr(self, name))
        if self.canonical_slot_key != self.canonical_slot_key.upper():
            raise InvalidProductionPlanningModelError("Identity slot key non canonica.")
        expected_sequences = {
            "PLAN": "PIANO_PRODUZIONE_ID",
            "REVISION": "REVISIONE_PIANO_PRODUZIONE_ID",
            "PLANNING_LINE": "RIGA_PIANO_SEMINA_ID",
            "ALLOCATION": "ALLOCAZIONE_ID",
            "REPLACEMENT_ALLOCATION": "ALLOCAZIONE_ID",
        }
        if expected_sequences.get(self.slot_kind) != self.sequence_name:
            raise InvalidProductionPlanningModelError("Identity slot kind/sequence incoerenti.")
        _version("identity slot position", self.position)

    @property
    def ordering_key(self) -> tuple[str, str, int]:
        return self.sequence_name, self.canonical_slot_key, self.position


@dataclass(frozen=True)
class ProductionPlanningIdentityBundle:
    """Identita gia allocate, consumate nell'ordine materiale dell'assembly."""

    plan_public_ids: tuple[PublicId, ...]
    revision_public_ids: tuple[PublicId, ...]
    planning_line_public_ids: tuple[PublicId, ...]
    allocation_public_ids: tuple[PublicId, ...]
    replacement_allocation_public_ids: tuple[PublicId, ...] = ()
    slot_assignments: tuple[tuple[ProductionPlanningIdentitySlot, PublicId], ...] = ()

    def __post_init__(self) -> None:
        for name, values, prefix in (
            ("plan_public_ids", self.plan_public_ids, "PP-"),
            ("revision_public_ids", self.revision_public_ids, "RVP-"),
            ("planning_line_public_ids", self.planning_line_public_ids, "RPS-"),
            ("allocation_public_ids", self.allocation_public_ids, "ALL-"),
            (
                "replacement_allocation_public_ids",
                self.replacement_allocation_public_ids,
                "ALL-",
            ),
        ):
            if not isinstance(values, tuple):
                raise InvalidProductionPlanningModelError(f"{name} deve essere una tuple.")
            if (
                any(
                    not isinstance(value, PublicId)
                    or not value.value.startswith(prefix)
                    for value in values
                )
                or tuple(item.value for item in values)
                != tuple(sorted(item.value for item in values))
                or len(set(values)) != len(values)
            ):
                raise InvalidProductionPlanningModelError(
                    f"{name} contiene identita duplicate o non valide."
                )
        if self.slot_assignments:
            slots = tuple(item[0] for item in self.slot_assignments)
            public_ids = tuple(item[1] for item in self.slot_assignments)
            if tuple(slot.ordering_key for slot in slots) != tuple(
                sorted(slot.ordering_key for slot in slots)
            ) or len(set(slots)) != len(slots):
                raise InvalidProductionPlanningModelError("Identity slot bundle non ordinato o duplicato.")
            if len(set(public_ids)) != len(public_ids):
                raise InvalidProductionPlanningModelError("Public ID duplicato nel bundle Identity.")

    @classmethod
    def from_slot_assignments(
        cls,
        assignments: tuple[tuple[ProductionPlanningIdentitySlot, PublicId], ...],
    ) -> ProductionPlanningIdentityBundle:
        by_kind: dict[str, list[PublicId]] = {
            "PLAN": [], "REVISION": [], "PLANNING_LINE": [],
            "ALLOCATION": [], "REPLACEMENT_ALLOCATION": [],
        }
        prefixes = {
            "PLAN": "PP-", "REVISION": "RVP-", "PLANNING_LINE": "RPS-",
            "ALLOCATION": "ALL-", "REPLACEMENT_ALLOCATION": "ALL-",
        }
        for slot, public_id in assignments:
            if slot.slot_kind not in by_kind or not public_id.value.startswith(prefixes[slot.slot_kind]):
                raise InvalidProductionPlanningModelError("Identity non coerente con lo slot.")
            by_kind[slot.slot_kind].append(public_id)
        return cls(
            *(tuple(by_kind[kind]) for kind in ("PLAN", "REVISION", "PLANNING_LINE", "ALLOCATION")),
            replacement_allocation_public_ids=tuple(by_kind["REPLACEMENT_ALLOCATION"]),
            slot_assignments=assignments,
        )


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

    def __post_init__(self) -> None:
        _resource_quantities(self.eligible, self.allocated, self.allocable_residual)
        _version("stock version", self.version)


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
class ProductionPlanningLoadedInput:
    snapshot: PlanningInputSnapshot
    allocation_disposition_decisions: tuple[AllocationDispositionDecision, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, PlanningInputSnapshot):
            raise InvalidProductionPlanningModelError("Loaded input privo di snapshot valido.")
        if not isinstance(self.allocation_disposition_decisions, tuple):
            raise InvalidProductionPlanningModelError("Disposition loaded input devono essere una tuple.")
        _unique_sorted(
            self.allocation_disposition_decisions,
            lambda item: item.allocation_public_id.value,
            "allocation disposition decisions",
        )


@dataclass(frozen=True)
class ProductionPlanningAssemblyInput:
    command: ProductionPlanningCommand
    run: ProductionPlanningRunSnapshot
    snapshot: PlanningInputSnapshot
    candidates: tuple[PlanningCandidate, ...]
    allocation_dispositions: tuple[AllocationDispositionDecision, ...]
    identities: ProductionPlanningIdentityBundle | None = None

    def __post_init__(self) -> None:
        if not isinstance(
            self.command, (InitialProductionPlanningCommand, ReplanProductionPlanningCommand)
        ):
            raise InvalidProductionPlanningModelError("Command assembly non valido.")
        if not isinstance(self.run, ProductionPlanningRunSnapshot) or self.run.state != "OPEN":
            raise InvalidProductionPlanningModelError("Assembly richiede una RUN OPEN.")
        if not isinstance(self.snapshot, PlanningInputSnapshot):
            raise InvalidProductionPlanningModelError("Snapshot assembly non valido.")
        if self.identities is not None and not isinstance(self.identities, ProductionPlanningIdentityBundle):
            raise InvalidProductionPlanningModelError("Identity bundle assembly non valido.")
        if self.command.business_at != self.snapshot.business_at:
            raise InvalidProductionPlanningModelError("business_at assembly incoerente.")
        if self.command.policy != self.snapshot.policy.reference:
            raise InvalidProductionPlanningModelError("Policy assembly incoerente.")
        if not isinstance(self.candidates, tuple) or not isinstance(
            self.allocation_dispositions, tuple
        ):
            raise InvalidProductionPlanningModelError(
                "Candidates e disposition devono essere tuple ordinate."
            )
        candidate_ids = tuple(
            item.demand.order_line_public_id.value for item in self.candidates
        )
        if len(candidate_ids) != len(set(candidate_ids)):
            raise InvalidProductionPlanningModelError(
                "assembly candidates contiene righe domanda duplicate."
            )
        _unique_sorted(
            self.allocation_dispositions,
            lambda item: item.allocation_public_id.value,
            "assembly allocation dispositions",
        )
        candidate_demands = {
            item.demand.order_line_public_id: item.demand for item in self.candidates
        }
        snapshot_demands = {
            item.order_line_public_id: item for item in self.snapshot.demands
        }
        if candidate_demands != snapshot_demands:
            raise InvalidProductionPlanningModelError(
                "Candidates non corrispondono field-by-field alle demands dello snapshot."
            )


@dataclass(frozen=True)
class ProductionPlanningAssemblyPlan:
    """Decisioni business definitive e template ID-free per la materializzazione."""

    command: ProductionPlanningCommand
    run: ProductionPlanningRunSnapshot
    snapshot: PlanningInputSnapshot
    candidates: tuple[PlanningCandidate, ...]
    allocation_dispositions: tuple[AllocationDispositionDecision, ...]
    identity_slots: tuple[ProductionPlanningIdentitySlot, ...]
    _materialization_template: object

    def __post_init__(self) -> None:
        if not isinstance(self.identity_slots, tuple) or not self.identity_slots:
            raise InvalidProductionPlanningModelError("Assembly plan privo di identity slot.")
        keys = tuple(slot.ordering_key for slot in self.identity_slots)
        if keys != tuple(sorted(keys)) or len(set(self.identity_slots)) != len(self.identity_slots):
            raise InvalidProductionPlanningModelError("Identity slot non canonici.")

    @property
    def revisions(self) -> tuple[PlanRevisionDraft, ...]:
        return self._materialization_template.revisions  # type: ignore[union-attr]

    @property
    def planning_lines(self) -> tuple[PlanningLineDraft, ...]:
        return tuple(line for revision in self.revisions for line in revision.lines)

    @property
    def seed_resources(self) -> tuple[SeedResourceDraft, ...]:
        return self._materialization_template.seed_resources  # type: ignore[union-attr]

    @property
    def allocations(self) -> tuple[AllocationDraft, ...]:
        return self._materialization_template.allocations  # type: ignore[union-attr]

    @property
    def allocation_transitions(self) -> tuple[AllocationTransitionDraft, ...]:
        return self._materialization_template.allocation_transitions  # type: ignore[union-attr]

    @property
    def counters(self) -> ProductionPlanningRunCounters:
        return self._materialization_template.counters  # type: ignore[union-attr]

    @property
    def messages(self) -> tuple[RunMessage, ...]:
        return self._materialization_template.messages  # type: ignore[union-attr]

    @property
    def audit_intents(self) -> tuple[AuditDraft, ...]:
        return self._materialization_template.audits  # type: ignore[union-attr]


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
    decision_set_key: CanonicalHash
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
        if not isinstance(self.decision_set_key, CanonicalHash):
            raise InvalidProductionPlanningModelError("Decision set key replanning non valida.")
        if canonical_frame(self.decision_set_key.value) not in self.canonical_text:
            raise InvalidProductionPlanningModelError(
                "Canonical replanning snapshot privo del decision set key."
            )
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
        if self.remaining_to_start != self.authorized_productive_quantity:
            raise InvalidProductionPlanningModelError("Quantita produttiva draft incoerente.")
        if self.quantitative_buffer_type not in BUFFER_TYPES:
            raise InvalidProductionPlanningModelError("Buffer riga piano non congelato.")
        if (self.quantitative_buffer_type == "NONE") != (self.quantitative_buffer_value is None):
            raise InvalidProductionPlanningModelError("Valore buffer riga piano incoerente.")
        for name in ("quantitative_buffer_value", "calculated_quantitative_buffer", "pre_granularity_quantity"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _decimal(name, value))
        if self.authorized_productive_quantity.value == 0 and (
            self.production_deficit.value != 0
            or self.calculated_quantitative_buffer != 0
            or self.pre_granularity_quantity != 0
            or self.remaining_to_start.value != 0
            or covered != self.candidate.demand.commercial_residual.value
        ):
            raise InvalidProductionPlanningModelError(
                "Produzione zero ammessa esclusivamente con coverage completa e calcolo zero."
            )
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
class AllocationReplacementSpecification:
    replacement_allocation_slot_key: str
    allocation_type: str
    source_public_id: PublicId
    destination_order_line_public_id: PublicId
    destination_planning_line_slot_key: str
    quantity: ExactQuantity
    provenance: str

    def __post_init__(self) -> None:
        if not all(isinstance(value, PublicId) for value in (
            self.source_public_id, self.destination_order_line_public_id,
        )) or not isinstance(self.quantity, ExactQuantity):
            raise InvalidProductionPlanningModelError(
                "Replacement allocation contiene riferimenti o quantità non validi."
            )
        _text("replacement allocation slot key", self.replacement_allocation_slot_key)
        _text("destination planning-line slot key", self.destination_planning_line_slot_key)
        destination_fields = parse_canonical_slot_key(
            self.destination_planning_line_slot_key,
            marker=PLANNING_LINE_SLOT_MARKER_V1, field_count=3,
        )
        if destination_fields[2] != self.destination_order_line_public_id.value:
            raise InvalidProductionPlanningModelError(
                "Destination planning-line slot key incoerente."
            )
        if self.allocation_type not in ALLOCATION_TYPES:
            raise InvalidProductionPlanningModelError("Tipo replacement allocation non congelato.")
        if self.quantity.value <= 0:
            raise InvalidProductionPlanningModelError("Quantità replacement deve essere positiva.")
        _text("replacement provenance", self.provenance)


@dataclass(frozen=True)
class AllocationDispositionDecision:
    allocation_public_id: PublicId
    expected_version: int
    disposition_cause: str
    source_usability: str
    observed_remaining_quantity: Decimal
    consumed_quantity_delta: Decimal
    target_disposition: str
    replacement_specification: AllocationReplacementSpecification | None
    reason: str
    provenance: str

    def __post_init__(self) -> None:
        _version("expected_version", self.expected_version)
        if self.disposition_cause not in ALLOCATION_DISPOSITION_CAUSES:
            raise InvalidProductionPlanningModelError("Causa disposition allocation non congelata.")
        if self.source_usability not in ALLOCATION_SOURCE_USABILITY:
            raise InvalidProductionPlanningModelError("Source usability allocation non congelata.")
        if self.target_disposition not in ALLOCATION_DISPOSITIONS:
            raise InvalidProductionPlanningModelError("Target disposition allocation non congelata.")
        object.__setattr__(
            self,
            "observed_remaining_quantity",
            _decimal("observed_remaining_quantity", self.observed_remaining_quantity, positive=True),
        )
        object.__setattr__(
            self,
            "consumed_quantity_delta",
            _decimal("consumed_quantity_delta", self.consumed_quantity_delta),
        )
        if self.consumed_quantity_delta >= self.observed_remaining_quantity:
            raise InvalidProductionPlanningModelError(
                "La disposition richiede una quota residua positiva dopo il consumo."
            )
        expected = {
            "RILASCIATA": ("REUSABLE", _RELEASE_CAUSES),
            "SOSTITUITA": ("TRANSFERABLE_ONLY", _TRANSFER_CAUSES),
            "INVALIDA": ("UNUSABLE", _INVALIDATION_CAUSES),
        }[self.target_disposition]
        if self.source_usability != expected[0] or self.disposition_cause not in expected[1]:
            raise InvalidProductionPlanningModelError(
                "Causa, source usability e target disposition non coerenti."
            )
        has_replacement = self.replacement_specification is not None
        if has_replacement and not isinstance(
            self.replacement_specification, AllocationReplacementSpecification
        ):
            raise InvalidProductionPlanningModelError("Replacement specification non valida.")
        if (self.target_disposition == "SOSTITUITA") != has_replacement:
            raise InvalidProductionPlanningModelError(
                "Replacement obbligatoria soltanto per SOSTITUITA."
            )
        if self.replacement_specification is not None:
            replacement = self.replacement_specification
            expected_slot_key = replacement_allocation_slot_key_v1(
                self.allocation_public_id, replacement.allocation_type,
                replacement.source_public_id,
                replacement.destination_order_line_public_id,
                replacement.destination_planning_line_slot_key,
            )
            if replacement.replacement_allocation_slot_key != expected_slot_key:
                raise InvalidProductionPlanningModelError(
                    "Replacement allocation slot key incoerente."
                )
            if replacement.quantity.value != self.disposition_quantity:
                raise InvalidProductionPlanningModelError(
                    "Quantità replacement diversa dal delta trasferito."
                )
        _text("disposition reason", self.reason)
        _text("disposition provenance", self.provenance)

    @property
    def disposition_quantity(self) -> Decimal:
        return self.observed_remaining_quantity - self.consumed_quantity_delta

    def to_transition_draft(
        self, snapshot: ActiveAllocationSnapshot
    ) -> AllocationTransitionDraft:
        if not isinstance(snapshot, ActiveAllocationSnapshot):
            raise InvalidProductionPlanningModelError("Active allocation snapshot non valido.")
        if (
            snapshot.allocation_public_id != self.allocation_public_id
            or snapshot.version != self.expected_version
            or snapshot.state != "ATTIVA"
            or snapshot.remaining_quantity.value != self.observed_remaining_quantity
        ):
            raise InvalidProductionPlanningModelError(
                "Disposition decision non coerente con ActiveAllocationSnapshot."
            )
        replacement = self.replacement_specification
        if replacement is not None and replacement.quantity.unit != snapshot.remaining_quantity.unit:
            raise InvalidProductionPlanningModelError("UOM replacement incoerente con il parent.")
        disposition_deltas = {
            "RILASCIATA": (self.disposition_quantity, Decimal("0"), Decimal("0")),
            "SOSTITUITA": (Decimal("0"), self.disposition_quantity, Decimal("0")),
            "INVALIDA": (Decimal("0"), Decimal("0"), self.disposition_quantity),
        }[self.target_disposition]
        return AllocationTransitionDraft(
            allocation_public_id=self.allocation_public_id,
            expected_version=self.expected_version,
            current_state="ATTIVA",
            target_state=self.target_disposition,
            observed_allocated_quantity=snapshot.allocated_quantity.value,
            observed_consumed_quantity=snapshot.consumed_quantity.value,
            observed_released_quantity=snapshot.released_quantity.value,
            observed_transferred_quantity=snapshot.transferred_quantity.value,
            observed_invalidated_quantity=snapshot.invalidated_quantity.value,
            observed_remaining_quantity=snapshot.remaining_quantity.value,
            consumed_quantity_delta=self.consumed_quantity_delta,
            released_quantity_delta=disposition_deltas[0],
            transferred_quantity_delta=disposition_deltas[1],
            invalidated_quantity_delta=disposition_deltas[2],
            replacement_allocation_slot_key=(
                replacement.replacement_allocation_slot_key if replacement else None
            ),
            replacement_allocation_public_id=None,
            reason=self.reason,
            provenance=self.provenance,
        )


def disposition_set_key_v1(
    *,
    previous_plan_revision_public_id: PublicId,
    order_line_public_id: PublicId,
    replanning_reason_code: str,
    correlation_id: str,
    decisions: tuple[AllocationDispositionDecision, ...],
) -> CanonicalHash:
    if replanning_reason_code not in REPLANNING_REASONS:
        raise InvalidProductionPlanningModelError("Reason disposition set non congelata.")
    _text("correlation_id", correlation_id)
    if not isinstance(decisions, tuple):
        raise InvalidProductionPlanningModelError("Disposition set decisions deve essere tuple.")
    ordered = tuple(sorted(decisions, key=lambda item: item.allocation_public_id.value))
    if ordered != decisions or len({item.allocation_public_id for item in decisions}) != len(decisions):
        raise InvalidProductionPlanningModelError("Disposition set non ordinato o duplicato.")
    records = []
    for decision in decisions:
        replacement = decision.replacement_specification
        records.append(canonical_record(
            decision.allocation_public_id.value,
            str(decision.expected_version),
            decision.disposition_cause,
            decision.source_usability,
            _canonical_decimal(decision.observed_remaining_quantity),
            _canonical_decimal(decision.consumed_quantity_delta),
            decision.target_disposition,
            decision.reason,
            decision.provenance,
            "true" if replacement is not None else "false",
            replacement.replacement_allocation_slot_key if replacement else None,
            replacement.destination_planning_line_slot_key if replacement else None,
            replacement.allocation_type if replacement else None,
            replacement.source_public_id.value if replacement else None,
            replacement.destination_order_line_public_id.value if replacement else None,
            _canonical_decimal(replacement.quantity.value) if replacement else None,
            replacement.quantity.unit.value if replacement else None,
            replacement.provenance if replacement else None,
        ))
    canonical = canonical_record(
        DISPOSITION_SET_MARKER_V1,
        previous_plan_revision_public_id.value,
        order_line_public_id.value,
        replanning_reason_code,
        correlation_id,
        canonical_list(tuple(records)),
    )
    return CanonicalHash(hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def _canonical_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


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
    replacement_allocation_slot_key: str | None
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
        replacement_references = sum(item is not None for item in (
            self.replacement_allocation_slot_key,
            self.replacement_allocation_public_id,
        ))
        if (self.transferred_quantity_delta > 0) != (replacement_references == 1):
            raise InvalidProductionPlanningModelError("Replacement incoerente con il transfer.")
        if self.replacement_allocation_slot_key is not None:
            _text("replacement_allocation_slot_key", self.replacement_allocation_slot_key)
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
        if not isinstance(self.seed_resources, tuple):
            raise InvalidProductionPlanningModelError("seed_resources deve essere una tuple ordinata.")
        _unique_sorted(
            self.seed_resources,
            lambda item: item.planning_line_public_id.value,
            "seed_resources",
        )
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
        lines = {
            line.public_id: line
            for revision in self.revisions
            for line in revision.lines
        }
        if len(lines) != generated_lines:
            raise InvalidProductionPlanningModelError("Planning line public ID duplicata nel write set.")
        seed_line_ids = {item.planning_line_public_id for item in self.seed_resources}
        if not seed_line_ids.issubset(lines):
            raise InvalidProductionPlanningModelError("SeedResourceDraft orfano.")
        expected_seed_line_ids = {
            public_id
            for public_id, line in lines.items()
            if line.authorized_productive_quantity.value > 0
        }
        if seed_line_ids != expected_seed_line_ids:
            raise InvalidProductionPlanningModelError(
                "Cardinalità SeedResourceDraft incoerente con la produzione autorizzata."
            )
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
        if self.run_state != "COMMITTED":
            raise InvalidProductionPlanningModelError(
                "ProductionPlanningResult rappresenta esclusivamente un commit certo."
            )
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


@dataclass(frozen=True)
class ProductionPlanningReconciliationRequiredResult:
    planning_run_public_id: PublicId
    run_state: str
    business_at: datetime
    observed_at: datetime
    correlation_id: str
    failure_category: str
    code: str
    message: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.planning_run_public_id, PublicId)
            or not self.planning_run_public_id.value.startswith("RPP-")
        ):
            raise InvalidProductionPlanningModelError("planning_run_public_id deve essere RPP-*.")
        if self.run_state != "RECONCILIATION_REQUIRED":
            raise InvalidProductionPlanningModelError(
                "Il risultato incerto richiede RECONCILIATION_REQUIRED."
            )
        _instant("business_at", self.business_at)
        _instant("observed_at", self.observed_at)
        _text("correlation_id", self.correlation_id)
        if self.failure_category != "RECONCILIATION_REQUIRED":
            raise InvalidProductionPlanningModelError(
                "Failure category del risultato incerto non valida."
            )
        _text("code", self.code)
        _text("message", self.message)


ProductionPlanningRunOutcome = (
    ProductionPlanningResult | ProductionPlanningReconciliationRequiredResult
)


def _resource_quantities(total: ExactQuantity, allocated: ExactQuantity, residual: ExactQuantity) -> None:
    if not all(isinstance(item, ExactQuantity) for item in (total, allocated, residual)):
        raise InvalidProductionPlanningModelError("Resource quantity non valida.")
    if len({total.unit, allocated.unit, residual.unit}) != 1 or allocated.value + residual.value != total.value:
        raise InvalidProductionPlanningModelError("Resource quantities incoerenti.")


def _unique_sorted(items: tuple[object, ...], key, name: str) -> None:
    keys = tuple(key(item) for item in items)
    if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
        raise InvalidProductionPlanningModelError(f"{name} deve essere unico e ordinato deterministicamente.")
