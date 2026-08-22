"""Assembler puro e deterministico del write set Production Planning V1."""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING
from enum import Enum
import hashlib

from .errors import ProductionPlanningError
from .models import (
    ActiveAllocationSnapshot,
    AllocationDraft,
    AuditDraft,
    CanonicalHash,
    CanonicalReplanningSnapshot,
    ExactQuantity,
    PlanRevisionDraft,
    PlanningCandidate,
    PlanningLineDraft,
    ProductionPlanningAssemblyPlan,
    ProductionPlanningAssemblyInput,
    ProductionPlanningCommit,
    ProductionPlanningIdentityBundle,
    ProductionPlanningIdentitySlot,
    ProductionPlanningRunCounters,
    PublicId,
    ReplanProductionPlanningCommand,
    SeedResourceDraft,
    disposition_set_key_v1,
    planning_line_slot_key_v1,
)


class ProductionPlanningCommitAssembler:
    """Separa decisioni business pure e assegnazione meccanica degli ID."""

    def plan(self, value: ProductionPlanningAssemblyInput) -> ProductionPlanningAssemblyPlan:
        if not isinstance(value, ProductionPlanningAssemblyInput):
            raise _input_error("INVALID_ASSEMBLY_INPUT", "Input assembly non valido.")
        if value.identities is not None:
            value = replace(value, identities=None)
        candidates = tuple(sorted(value.candidates, key=_candidate_order))
        allocation_capacity = len(candidates) + len(value.snapshot.stock) + len(
            value.snapshot.harvests
        ) + len(value.snapshot.in_progress)
        replacement_keys = tuple(sorted(
            decision.replacement_specification.replacement_allocation_slot_key
            for decision in value.allocation_dispositions
            if decision.replacement_specification is not None
        ))
        replacement_placeholders = tuple(
            PublicId(f"ALL-{950000 + index:06d}")
            for index in range(len(replacement_keys))
        )
        plan_ids = (
            (value.snapshot.current_plans[0].plan_public_id,)
            if isinstance(value.command, ReplanProductionPlanningCommand)
            else (PublicId("PP-900000"),)
        )
        placeholders = ProductionPlanningIdentityBundle(
            plan_ids,
            (PublicId("RVP-900000"),),
            tuple(PublicId(f"RPS-{900000 + index:06d}") for index in range(len(candidates))),
            tuple(PublicId(f"ALL-{900000 + index:06d}") for index in range(allocation_capacity)),
            replacement_placeholders,
        )
        template = self._assemble_with_identities(
            replace(value, candidates=candidates, identities=placeholders),
            allow_unused_identities=True,
        )
        generated_allocation_ids = tuple(
            item.public_id for item in template.allocations
            if item.public_id in placeholders.allocation_public_ids
        )
        slots = []
        for sequence_name, kind, values in (
            ("ALLOCAZIONE_ID", "ALLOCATION", generated_allocation_ids),
            ("ALLOCAZIONE_ID", "REPLACEMENT_ALLOCATION", replacement_keys),
            ("PIANO_PRODUZIONE_ID", "PLAN", () if isinstance(value.command, ReplanProductionPlanningCommand) else placeholders.plan_public_ids),
            ("REVISIONE_PIANO_PRODUZIONE_ID", "REVISION", placeholders.revision_public_ids),
            ("RIGA_PIANO_SEMINA_ID", "PLANNING_LINE", placeholders.planning_line_public_ids),
        ):
            for position, slot_value in enumerate(values):
                canonical_slot_key = f"{kind}:{position:06d}"
                if kind == "REPLACEMENT_ALLOCATION":
                    canonical_slot_key = slot_value
                slots.append(
                    ProductionPlanningIdentitySlot(
                        sequence_name, kind, canonical_slot_key, position
                    )
                )
        if isinstance(value.command, ReplanProductionPlanningCommand):
            slots = [slot for slot in slots if slot.slot_kind != "PLANNING_LINE"]
            line_keys = sorted(
                planning_line_slot_key_v1(
                    value.command.previous_revision_public_id,
                    candidate.demand.order_line_public_id,
                )
                for candidate in candidates
            )
            slots.extend(
                ProductionPlanningIdentitySlot(
                    "RIGA_PIANO_SEMINA_ID", "PLANNING_LINE", key, position
                )
                for position, key in enumerate(line_keys)
            )
        return ProductionPlanningAssemblyPlan(
            value.command,
            value.run,
            value.snapshot,
            candidates,
            value.allocation_dispositions,
            tuple(sorted(slots, key=lambda item: item.ordering_key)),
            template,
        )

    def materialize(
        self,
        assembly_plan: ProductionPlanningAssemblyPlan,
        identity_bundle: ProductionPlanningIdentityBundle,
    ) -> ProductionPlanningCommit:
        if not isinstance(assembly_plan, ProductionPlanningAssemblyPlan):
            raise _input_error("INVALID_ASSEMBLY_PLAN", "Assembly plan non valido.")
        if not isinstance(identity_bundle, ProductionPlanningIdentityBundle):
            raise _input_error("INVALID_IDENTITY_BUNDLE", "Identity bundle non valido.")
        expected = assembly_plan.identity_slots
        actual = tuple(item[0] for item in identity_bundle.slot_assignments)
        if actual != expected:
            missing = set(expected) - set(actual)
            extra = set(actual) - set(expected)
            code = "IDENTITY_SLOT_MISSING" if missing else "IDENTITY_SLOT_EXTRA" if extra else "IDENTITY_SLOT_ORDER_MISMATCH"
            raise _input_error(code, "Identity bundle non coincide con gli slot canonici.")
        template = assembly_plan._materialization_template
        replacement_keys = tuple(sorted(
            decision.replacement_specification.replacement_allocation_slot_key
            for decision in assembly_plan.allocation_dispositions
            if decision.replacement_specification is not None
        ))
        replacement_placeholders = tuple(
            item.public_id for item in template.allocations
            if item.public_id.value.startswith("ALL-95")
        )
        placeholder_by_slot = {
            "PLAN": tuple(item.plan_public_id for item in template.revisions),
            "REVISION": tuple(item.revision_public_id for item in template.revisions),
            "PLANNING_LINE": tuple(line.public_id for revision in template.revisions for line in revision.lines),
            "ALLOCATION": tuple(
                item.public_id for item in template.allocations
                if item.public_id not in replacement_placeholders
            ),
            "REPLACEMENT_ALLOCATION": replacement_placeholders,
        }
        placeholders_by_key = {}
        if isinstance(assembly_plan.command, ReplanProductionPlanningCommand):
            for candidate, line in zip(assembly_plan.candidates, template.revisions[0].lines):
                key = planning_line_slot_key_v1(
                    assembly_plan.command.previous_revision_public_id,
                    candidate.demand.order_line_public_id,
                )
                placeholders_by_key[("PLANNING_LINE", key)] = line.public_id
        for key, placeholder in zip(replacement_keys, replacement_placeholders):
            placeholders_by_key[("REPLACEMENT_ALLOCATION", key)] = placeholder
        mapping = {}
        for slot, public_id in identity_bundle.slot_assignments:
            placeholder = placeholders_by_key.get((slot.slot_kind, slot.canonical_slot_key))
            if placeholder is None:
                placeholder = placeholder_by_slot[slot.slot_kind][slot.position]
            mapping[placeholder.value] = public_id.value
        return _replace_identity_values(template, mapping)

    def assemble(self, value: ProductionPlanningAssemblyInput) -> ProductionPlanningCommit:
        if value.identities is None:
            raise _input_error("IDENTITY_BUNDLE_REQUIRED", "assemble richiede Identity preallocate.")
        plan = self.plan(replace(value, identities=None))
        assignments = []
        ids_by_kind = {
            "PLAN": value.identities.plan_public_ids,
            "REVISION": value.identities.revision_public_ids,
            "PLANNING_LINE": value.identities.planning_line_public_ids,
            "ALLOCATION": value.identities.allocation_public_ids,
            "REPLACEMENT_ALLOCATION": value.identities.replacement_allocation_public_ids,
        }
        positions = {kind: 0 for kind in ids_by_kind}
        for slot in plan.identity_slots:
            values = ids_by_kind[slot.slot_kind]
            position = positions[slot.slot_kind]
            if position >= len(values):
                raise _input_error("IDENTITY_CARDINALITY_MISMATCH", "Identita insufficienti.")
            assignments.append((slot, values[position]))
            positions[slot.slot_kind] += 1
        if any(
            positions[kind] != len(values)
            for kind, values in ids_by_kind.items()
            if not (kind == "PLAN" and isinstance(value.command, ReplanProductionPlanningCommand))
        ):
            raise _input_error("IDENTITY_CARDINALITY_MISMATCH", "Identita inutilizzate.")
        bundle = ProductionPlanningIdentityBundle.from_slot_assignments(tuple(assignments))
        return self.materialize(plan, bundle)

    def _assemble_with_identities(
        self, value: ProductionPlanningAssemblyInput, *, allow_unused_identities: bool = False
    ) -> ProductionPlanningCommit:
        if not isinstance(value, ProductionPlanningAssemblyInput):
            raise _input_error("INVALID_ASSEMBLY_INPUT", "Input assembly non valido.")

        candidates = tuple(sorted(value.candidates, key=_candidate_order))
        if not candidates:
            raise _infeasible("NO_ELIGIBLE_DEMAND", "Nessuna domanda eleggibile da pianificare.")
        ordered_groups = (("PRODUCTION_PLANNING_V1", candidates),)

        identities = value.identities
        assert identities is not None
        if len(identities.plan_public_ids) != len(ordered_groups):
            raise _input_error("IDENTITY_CARDINALITY_MISMATCH", "Numero identita piano incoerente.")
        if len(identities.revision_public_ids) != len(ordered_groups):
            raise _input_error("IDENTITY_CARDINALITY_MISMATCH", "Numero identita revisione incoerente.")
        if len(identities.planning_line_public_ids) != len(candidates):
            raise _input_error("IDENTITY_CARDINALITY_MISMATCH", "Numero identita riga incoerente.")
        replacement_specs = tuple(sorted(
            (
                decision.replacement_specification
                for decision in value.allocation_dispositions
                if decision.replacement_specification is not None
            ),
            key=lambda item: item.replacement_allocation_slot_key,
        ))
        if len(identities.replacement_allocation_public_ids) != len(replacement_specs):
            raise _input_error(
                "IDENTITY_CARDINALITY_MISMATCH",
                "Identity replacement non coincidono con le disposition.",
            )
        replacement_ids = {
            specification.replacement_allocation_slot_key: public_id
            for specification, public_id in zip(
                replacement_specs, identities.replacement_allocation_public_ids
            )
        }

        allocation_ids = iter(identities.allocation_public_ids)
        line_ids = iter(identities.planning_line_public_ids)
        revisions: list[PlanRevisionDraft] = []
        seed_resources: list[SeedResourceDraft] = []
        allocations: list[AllocationDraft] = []
        lines_by_order_line: dict[str, PlanningLineDraft] = {}
        fully_covered = 0
        partially_covered = 0
        resource_remaining = _resource_remaining(value)

        for group_index, (_, group) in enumerate(ordered_groups):
            lines: list[PlanningLineDraft] = []
            for candidate in group:
                line_id = next(line_ids)
                line, coverage_allocations, seed, is_full, is_partial = self._assemble_line(
                    value, candidate, line_id, allocation_ids, resource_remaining
                )
                lines.append(line)
                allocations.extend(coverage_allocations)
                if seed is not None:
                    seed_resources.append(seed)
                fully_covered += int(is_full)
                partially_covered += int(is_partial)
                lines_by_order_line[candidate.demand.order_line_public_id.value] = line

            lines_tuple = tuple(sorted(lines, key=lambda item: item.public_id.value))
            plan_id = identities.plan_public_ids[group_index]
            revision_id = identities.revision_public_ids[group_index]
            revisions.append(
                self._revision(value, plan_id, revision_id, lines_tuple)
            )

        if not allow_unused_identities:
            try:
                next(allocation_ids)
            except StopIteration:
                pass
            else:
                raise _input_error("IDENTITY_CARDINALITY_MISMATCH", "Identita allocazione inutilizzate.")

        transitions = []
        active = {item.allocation_public_id: item for item in value.snapshot.allocations}
        for decision in value.allocation_dispositions:
            snapshot = active.get(decision.allocation_public_id)
            if snapshot is None:
                raise _allocation_error("ALLOCATION_NOT_OBSERVED", "Allocazione disposition non osservata.")
            transition = decision.to_transition_draft(snapshot)
            transitions.append(transition)
            replacement = decision.replacement_specification
            if replacement is not None:
                destination_line = lines_by_order_line.get(
                    replacement.destination_order_line_public_id.value
                )
                expected_line_slot = planning_line_slot_key_v1(
                    value.command.previous_revision_public_id,
                    replacement.destination_order_line_public_id,
                ) if isinstance(value.command, ReplanProductionPlanningCommand) else None
                if (
                    destination_line is None
                    or replacement.destination_planning_line_slot_key != expected_line_slot
                ):
                    raise _allocation_error(
                        "REPLACEMENT_DESTINATION_INVALID",
                        "Replacement priva di riga Planning della revisione corrente.",
                    )
                replacement_public_id = replacement_ids[
                    replacement.replacement_allocation_slot_key
                ]
                transitions[-1] = replace(
                    transition,
                    replacement_allocation_slot_key=None,
                    replacement_allocation_public_id=replacement_public_id,
                )
                allocations.append(
                    AllocationDraft(
                        public_id=replacement_public_id,
                        allocation_type=replacement.allocation_type,
                        planning_line_public_id=destination_line.public_id,
                        source_public_id=replacement.source_public_id,
                        destination_order_line_public_id=replacement.destination_order_line_public_id,
                        quantity=replacement.quantity,
                    )
                )

        revisions_tuple = tuple(sorted(revisions, key=lambda item: item.plan_public_id.value))
        allocations_tuple = tuple(sorted(allocations, key=lambda item: item.public_id.value))
        transitions_tuple = tuple(
            sorted(transitions, key=lambda item: item.allocation_public_id.value)
        )
        seed_tuple = tuple(
            sorted(seed_resources, key=lambda item: item.planning_line_public_id.value)
        )
        counters = ProductionPlanningRunCounters(
            orders_read=len({item.demand.order_public_id for item in candidates}),
            order_lines_evaluated=len(candidates),
            lines_fully_covered=fully_covered,
            lines_partially_covered=partially_covered,
            planning_lines_generated=len(candidates),
            allocations_generated=len(allocations_tuple),
            late_lines=0,
            non_producible_lines=0,
            skipped_items=0,
        )
        audits = _audits(
            value, revisions_tuple, seed_tuple, allocations_tuple, transitions_tuple,
            counters,
        )
        return ProductionPlanningCommit(
            run=value.run,
            policy=value.snapshot.policy.reference,
            business_at=value.snapshot.business_at,
            context=value.command.context,
            revisions=revisions_tuple,
            seed_resources=seed_tuple,
            allocations=allocations_tuple,
            allocation_transitions=transitions_tuple,
            messages=(),
            counters=counters,
            audits=audits,
            input_snapshot=value.snapshot,
        )

    def _assemble_line(
        self,
        assembly: ProductionPlanningAssemblyInput,
        candidate: PlanningCandidate,
        line_id,
        allocation_ids,
        resource_remaining,
    ):
        demand = candidate.demand
        remaining = demand.commercial_residual.value
        unit = demand.commercial_residual.unit
        selected: list[tuple[str, object, Decimal]] = []

        classes = (
            ("STOCK", _stock_resources(assembly, candidate)),
            ("RACCOLTA", _harvest_resources(assembly, candidate)),
            ("PRODUZIONE_IN_CORSO", _in_progress_resources(assembly, candidate)),
        )
        coverage = {"STOCK": Decimal("0"), "RACCOLTA": Decimal("0"), "PRODUZIONE_IN_CORSO": Decimal("0")}
        for allocation_type, resources in classes:
            for resource in resources:
                if remaining == 0:
                    break
                resource_key = (allocation_type, resource[0])
                residual = resource_remaining[resource_key]
                amount = min(remaining, residual)
                if amount <= 0:
                    continue
                selected.append((allocation_type, resource[0], amount))
                coverage[allocation_type] += amount
                resource_remaining[resource_key] -= amount
                remaining -= amount

        deficit = remaining
        calculated_buffer, pre_granularity, productive = _production_quantity(
            deficit, assembly.snapshot.policy.quantitative_buffer_type,
            assembly.snapshot.policy.quantitative_buffer_value,
            candidate.knowledge.production_granularity,
        )
        planning_key = _planning_key(candidate, assembly)
        line = PlanningLineDraft(
            public_id=line_id,
            candidate=candidate,
            state="PIANIFICATA",
            planning_key=planning_key,
            expected_order_version=demand.order_version,
            expected_order_line_version=demand.order_line_version,
            stock_coverage=ExactQuantity(coverage["STOCK"], unit),
            in_progress_coverage=ExactQuantity(coverage["PRODUZIONE_IN_CORSO"], unit),
            allocated_harvest_coverage=ExactQuantity(coverage["RACCOLTA"], unit),
            production_deficit=ExactQuantity(deficit, unit),
            quantitative_buffer_type=assembly.snapshot.policy.quantitative_buffer_type,
            quantitative_buffer_value=assembly.snapshot.policy.quantitative_buffer_value,
            calculated_quantitative_buffer=calculated_buffer,
            pre_granularity_quantity=pre_granularity,
            authorized_productive_quantity=ExactQuantity(productive, unit),
            remaining_to_start=ExactQuantity(productive, unit),
            harvest_window_start=(
                demand.delivery_date
                - _days(candidate.knowledge.harvest_max_lead_days)
            ),
            harvest_window_end=(
                demand.delivery_date
                - _days(candidate.knowledge.harvest_min_lead_days)
            ),
        )
        created_allocations = []
        for allocation_type, source_id, amount in selected:
            created_allocations.append(
                AllocationDraft(
                    public_id=_next_allocation_id(allocation_ids),
                    allocation_type=allocation_type,
                    planning_line_public_id=line_id,
                    source_public_id=source_id,
                    destination_order_line_public_id=demand.order_line_public_id,
                    quantity=ExactQuantity(amount, unit),
                )
            )
        if productive > 0:
            created_allocations.append(
                AllocationDraft(
                    public_id=_next_allocation_id(allocation_ids),
                    allocation_type="DOMANDA",
                    planning_line_public_id=line_id,
                    source_public_id=demand.order_line_public_id,
                    destination_order_line_public_id=demand.order_line_public_id,
                    quantity=ExactQuantity(productive, unit),
                )
            )
            seed = SeedResourceDraft(
                planning_line_public_id=line_id,
                required_grams=productive * candidate.knowledge.seed_grams_per_set,
                grams_per_set=candidate.knowledge.seed_grams_per_set,
            )
        else:
            seed = None
        covered = demand.commercial_residual.value - deficit
        return (
            line,
            created_allocations,
            seed,
            covered == demand.commercial_residual.value,
            Decimal("0") < covered < demand.commercial_residual.value,
        )

    def _revision(self, assembly, plan_id, revision_id, lines):
        if not isinstance(assembly.command, ReplanProductionPlanningCommand):
            return PlanRevisionDraft(
                plan_public_id=plan_id,
                revision_public_id=revision_id,
                revision_number=1,
                request_key=_initial_revision_key(lines, assembly),
                lines=lines,
                plan_state="APERTO",
            )
        command = assembly.command
        target = next(
            (line for line in lines if line.candidate.demand.order_line_public_id == command.order_line_public_id),
            None,
        )
        if target is None:
            raise _input_error("REPLANNING_TARGET_MISSING", "Riga target replanning assente.")
        current_line = next(
            (item for item in assembly.snapshot.current_planning_lines if item.order_line_public_id == command.order_line_public_id),
            None,
        )
        current_plan = next(
            (item for item in assembly.snapshot.current_plans if current_line is not None and item.current_revision_public_id == current_line.revision_public_id),
            None,
        )
        if current_line is None or current_plan is None or current_plan.current_revision_public_id != command.previous_revision_public_id:
            raise _input_error("REPLANNING_SCOPE_INVALID", "Scope corrente replanning incoerente.")
        if plan_id != current_plan.plan_public_id:
            raise _input_error("REPLANNING_SCOPE_INVALID", "Identity piano replanning incoerente.")
        canonical = _replanning_snapshot(assembly, target, current_plan.current_revision_version)
        return PlanRevisionDraft(
            plan_public_id=current_plan.plan_public_id,
            revision_public_id=revision_id,
            revision_number=current_plan.revision_number + 1,
            request_key=canonical.replanning_key_v1,
            lines=lines,
            plan_state="APERTO",
            expected_plan_version=current_plan.plan_version,
            expected_current_revision_version=current_plan.current_revision_version,
            previous_revision_public_id=current_plan.current_revision_public_id,
            replanning_reason_code=command.replanning_reason_code,
            canonical_replanning_snapshot=canonical,
        )


def assemble(value: ProductionPlanningAssemblyInput) -> ProductionPlanningCommit:
    return ProductionPlanningCommitAssembler().assemble(value)


def _replace_identity_values(value, mapping):
    """Sostituisce soltanto slot simbolici; non esegue decisioni business."""
    if isinstance(value, PublicId):
        return PublicId(mapping.get(value.value, value.value))
    if isinstance(value, Enum):
        return value
    if isinstance(value, str):
        result = value
        for old, new in mapping.items():
            result = result.replace(old, new)
        return result
    if isinstance(value, tuple):
        return tuple(_replace_identity_values(item, mapping) for item in value)
    if is_dataclass(value):
        return replace(
            value,
            **{
                field.name: _replace_identity_values(getattr(value, field.name), mapping)
                for field in fields(value)
            },
        )
    return value


def _stock_resources(assembly, candidate):
    values = []
    for resource in assembly.snapshot.stock:
        if resource.variety_public_id != candidate.demand.variety_public_id:
            continue
        _same_uom(candidate, resource.allocable_residual)
        if resource.readiness_code != "READY":
            raise _infeasible("RESOURCE_NOT_READY", "STOCK non ready nello snapshot eleggibile.")
        values.append((resource.resource_public_id, assembly.snapshot.business_at, resource.allocable_residual.value, resource.allocated.value))
    return _ordered_resources(values)


def _harvest_resources(assembly, candidate):
    values = []
    for resource in assembly.snapshot.harvests:
        if resource.variety_public_id != candidate.demand.variety_public_id:
            continue
        _same_uom(candidate, resource.allocable_residual)
        if resource.harvested_at > assembly.snapshot.business_at:
            raise _infeasible("RESOURCE_NOT_READY", "RACCOLTA futura nello snapshot eleggibile.")
        values.append((resource.harvest_public_id, resource.harvested_at, resource.allocable_residual.value, resource.allocated.value))
    return _ordered_resources(values)


def _in_progress_resources(assembly, candidate):
    values = []
    for resource in assembly.snapshot.in_progress:
        if resource.variety_public_id != candidate.demand.variety_public_id:
            continue
        _same_uom(candidate, resource.allocable_residual)
        if resource.harvest_window_start.date() > candidate.demand.delivery_date or resource.state.value == "CHIUSA":
            raise _infeasible("RESOURCE_NOT_READY", "SEMINA non eleggibile entro la consegna.")
        values.append((resource.semina_public_id, resource.harvest_window_start, resource.allocable_residual.value, resource.allocated.value))
    return _ordered_resources(values)


def _ordered_resources(values):
    return tuple(sorted(values, key=lambda item: (item[1], item[3], -item[2], item[0].value)))


def _candidate_order(candidate):
    demand = candidate.demand
    priority = demand.commercial_priority
    return (
        demand.delivery_date,
        priority is None,
        priority if priority is not None else 0,
        demand.order_public_id.value,
        demand.order_line_public_id.value,
    )


def _resource_remaining(assembly):
    remaining = {}
    for allocation_type, values, id_name in (
        ("STOCK", assembly.snapshot.stock, "resource_public_id"),
        ("RACCOLTA", assembly.snapshot.harvests, "harvest_public_id"),
        ("PRODUZIONE_IN_CORSO", assembly.snapshot.in_progress, "semina_public_id"),
    ):
        for value in values:
            remaining[(allocation_type, getattr(value, id_name))] = value.allocable_residual.value
    return remaining


def _same_uom(candidate, quantity):
    if quantity.unit != candidate.demand.commercial_residual.unit:
        raise _input_error("RESOURCE_UOM_MISMATCH", "UOM risorsa diversa dalla domanda.")


def _production_quantity(deficit, buffer_type, buffer_value, granularity):
    if deficit == 0:
        return Decimal("0"), Decimal("0"), Decimal("0")
    if buffer_type == "NONE":
        calculated = Decimal("0")
    elif buffer_type == "PERCENTAGE":
        assert buffer_value is not None
        calculated = deficit * buffer_value
    else:
        assert buffer_value is not None
        calculated = buffer_value
    pre_granularity = deficit + calculated
    productive = (
        (pre_granularity / granularity).to_integral_value(rounding=ROUND_CEILING)
        * granularity
    )
    return calculated, pre_granularity, productive


def _next_allocation_id(values):
    try:
        return next(values)
    except StopIteration as exc:
        raise _input_error("IDENTITY_CARDINALITY_MISMATCH", "Identita allocazione insufficienti.") from exc


def _planning_key(candidate, assembly):
    demand = candidate.demand
    return _hash(
        _record(
            "production-planning-v1",
            demand.order_line_public_id.value,
            _decimal_text(demand.commercial_residual.value),
            demand.delivery_date.isoformat(),
            candidate.knowledge.protocol_version_public_id.value,
            assembly.snapshot.policy.reference.policy_set_code,
            str(assembly.snapshot.policy.reference.version),
        )
    )


def _initial_revision_key(lines, assembly):
    keys = tuple(sorted(line.planning_key.value for line in lines))
    text = _record(
        "production-planning-revision-v1",
        assembly.snapshot.policy.reference.policy_set_code,
        str(assembly.snapshot.policy.reference.version),
        str(len(keys)),
    ) + _list(keys)
    return _hash(text)


def _replanning_snapshot(assembly, line, previous_version):
    command = assembly.command
    assert isinstance(command, ReplanProductionPlanningCommand)
    demand = line.candidate.demand
    knowledge = line.candidate.knowledge
    stock = tuple(item for item in assembly.snapshot.stock if item.variety_public_id == demand.variety_public_id)
    progress = tuple(item for item in assembly.snapshot.in_progress if item.variety_public_id == demand.variety_public_id)
    allocations = tuple(item for item in assembly.snapshot.allocations if item.destination_order_line_public_id == demand.order_line_public_id)
    decision_set_key = disposition_set_key_v1(
        previous_plan_revision_public_id=command.previous_revision_public_id,
        order_line_public_id=demand.order_line_public_id,
        replanning_reason_code=command.replanning_reason_code,
        correlation_id=command.context.correlation_id,
        decisions=assembly.allocation_dispositions,
    )
    canonical_text = _record(
        "production-replanning-snapshot-v1",
        command.previous_revision_public_id.value,
        str(previous_version),
        demand.order_line_public_id.value,
        demand.order_public_id.value,
        demand.order_state.value,
        str(demand.order_version),
        str(demand.order_line_version),
        _decimal_text(demand.ordered.value),
        _decimal_text(demand.delivered.value),
        _decimal_text(demand.commercial_residual.value),
        demand.delivery_date.isoformat(),
        demand.variety_public_id.value,
        knowledge.protocol_version_public_id.value,
        str(knowledge.protocol_version_number),
        knowledge.valid_from.isoformat(),
        knowledge.valid_to.isoformat() if knowledge.valid_to else None,
        command.replanning_reason_code,
        assembly.snapshot.policy.reference.policy_set_code,
        str(assembly.snapshot.policy.reference.version),
        assembly.snapshot.policy.quantitative_buffer_type,
        _decimal_text(assembly.snapshot.policy.quantitative_buffer_value) if assembly.snapshot.policy.quantitative_buffer_value is not None else None,
        str(knowledge.temporal_buffer_minutes),
        _decimal_text(knowledge.production_granularity),
        decision_set_key.value,
    ) + _snapshot_collections(stock, progress, allocations)
    snapshot_hash = _hash(canonical_text)
    replanning_key = _hash(
        _record(
            "production-replanning-v1",
            command.previous_revision_public_id.value,
            demand.order_line_public_id.value,
            command.replanning_reason_code,
            canonical_text,
            assembly.snapshot.policy.reference.policy_set_code,
            str(assembly.snapshot.policy.reference.version),
        )
    )
    return CanonicalReplanningSnapshot(
        previous_revision_public_id=command.previous_revision_public_id,
        previous_plan_revision_version=previous_version,
        order_line_public_id=demand.order_line_public_id,
        order_public_id=demand.order_public_id,
        order_state=demand.order_state,
        order_version=demand.order_version,
        order_line_version=demand.order_line_version,
        ordered_quantity=demand.ordered,
        delivered_quantity=demand.delivered,
        commercial_residual_quantity=demand.commercial_residual,
        delivery_date=demand.delivery_date,
        variety_public_id=demand.variety_public_id,
        protocol_version_public_id=knowledge.protocol_version_public_id,
        protocol_version_number=knowledge.protocol_version_number,
        protocol_valid_from=knowledge.valid_from,
        protocol_valid_to=knowledge.valid_to,
        reason_code=command.replanning_reason_code,
        policy=assembly.snapshot.policy.reference,
        quantitative_buffer_type=assembly.snapshot.policy.quantitative_buffer_type,
        quantitative_buffer_value=assembly.snapshot.policy.quantitative_buffer_value,
        temporal_buffer_minutes=knowledge.temporal_buffer_minutes,
        production_granularity=knowledge.production_granularity,
        stock=stock,
        in_progress=progress,
        allocations=allocations,
        decision_set_key=decision_set_key,
        canonical_text=canonical_text,
        canonical_snapshot_hash=snapshot_hash,
        replanning_key_v1=replanning_key,
    )


def _snapshot_collections(stock, progress, allocations):
    stock_values = tuple(
        _record(item.resource_public_id.value, _decimal_text(item.eligible.value), _decimal_text(item.allocated.value), _decimal_text(item.allocable_residual.value), str(item.version), item.readiness_code)
        for item in stock
    )
    progress_values = tuple(
        _record(item.semina_public_id.value, item.protocol_version_public_id.value, _decimal_text(item.expected_useful.value), _decimal_text(item.allocated.value), _decimal_text(item.allocable_residual.value), _instant_text(item.harvest_window_start), _instant_text(item.harvest_window_end), item.state.value, str(item.version))
        for item in progress
    )
    allocation_values = tuple(
        _record(item.allocation_public_id.value, item.allocation_type, item.source_public_id.value, _decimal_text(item.allocated_quantity.value), _decimal_text(item.consumed_quantity.value), _decimal_text(item.released_quantity.value), _decimal_text(item.transferred_quantity.value), _decimal_text(item.invalidated_quantity.value), _decimal_text(item.remaining_quantity.value), item.state, str(item.version))
        for item in allocations
    )
    return _list(stock_values) + _list(progress_values) + _list(allocation_values)


def _audits(assembly, revisions, seeds, allocations, transitions, counters):
    audits = []
    for revision in revisions:
        audits.append(_audit("PIANO_PRODUZIONE", revision.plan_public_id, "INSERT" if revision.revision_number == 1 else "UPDATE", (), (("current_revision_public_id", revision.revision_public_id.value), ("state", revision.plan_state)), "production-planning:piano"))
        audits.append(_audit("PIANO_PRODUZIONE_REVISIONE", revision.revision_public_id, "INSERT", (), (("line_count", str(len(revision.lines))), ("plan_public_id", revision.plan_public_id.value), ("request_key", revision.request_key.value), ("revision_number", str(revision.revision_number))), "production-planning:revisione"))
        for line in revision.lines:
            demand = line.candidate.demand
            audits.append(_audit("RIGA_PIANO_SEMINA", line.public_id, "INSERT", (), (("authorized_productive_quantity", _decimal_text(line.authorized_productive_quantity.value)), ("commercial_residual", _decimal_text(demand.commercial_residual.value)), ("delivery_date", demand.delivery_date.isoformat()), ("order_line_public_id", demand.order_line_public_id.value), ("planning_key", line.planning_key.value), ("production_deficit", _decimal_text(line.production_deficit.value)), ("protocol_version_public_id", line.candidate.knowledge.protocol_version_public_id.value), ("state", line.state), ("unit", demand.commercial_residual.unit.value)), line.candidate.provenance))
    for seed in seeds:
        audits.append(_audit("RISORSA_SEME_PIANIFICATA", seed.planning_line_public_id, "INSERT", (), (("grams_per_set", _decimal_text(seed.grams_per_set)), ("required_grams", _decimal_text(seed.required_grams)), ("unit", "GRAM")), "production-planning:seed-resource"))
    for allocation in allocations:
        audits.append(_audit("ALLOCAZIONE", allocation.public_id, "INSERT", (), (("destination_order_line_public_id", allocation.destination_order_line_public_id.value), ("planning_line_public_id", allocation.planning_line_public_id.value), ("quantity", _decimal_text(allocation.quantity.value)), ("source_public_id", allocation.source_public_id.value), ("state", allocation.state), ("type", allocation.allocation_type), ("unit", allocation.quantity.unit.value)), "production-planning:allocation"))
    for transition in transitions:
        audits.append(_audit("ALLOCAZIONE", transition.allocation_public_id, "STATE_TRANSITION", (("remaining", _decimal_text(transition.observed_remaining_quantity)), ("state", transition.current_state)), (("remaining", _decimal_text(transition.expected_remaining_after)), ("state", transition.target_state)), transition.provenance))
    audits.append(_audit("PRODUCTION_PLANNING_RUN", assembly.run.public_id, "STATE_TRANSITION", (("state", "OPEN"),), (("allocations_generated", str(counters.allocations_generated)), ("order_lines_evaluated", str(counters.order_lines_evaluated)), ("planning_lines_generated", str(counters.planning_lines_generated)), ("state", "COMMITTED")), "production-planning:run"))
    return tuple(sorted(audits, key=lambda item: (item.entity_type, item.entity_public_id.value, item.operation)))


def _audit(entity_type, public_id, operation, before, after, provenance):
    return AuditDraft(entity_type, public_id, operation, tuple(sorted(before)), tuple(sorted(after)), provenance)


def _record(*values):
    return "".join(_frame(value) for value in values)


def _frame(value):
    if value is None:
        return "-1:"
    encoded = value.encode("utf-8")
    return f"{len(encoded)}:{value}"


def _list(values):
    return f"{len(values)};" + "".join(_frame(value) for value in values)


def _hash(value):
    return CanonicalHash(hashlib.sha256(value.encode("utf-8")).hexdigest())


def _decimal_text(value):
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def _instant_text(value: datetime):
    return value.isoformat(timespec="minutes")


def _days(value):
    return timedelta(days=value)


def _input_error(code, message):
    return ProductionPlanningError("PLANNING_INPUT_INVALID", code, message)


def _infeasible(code, message):
    return ProductionPlanningError("PLANNING_INFEASIBLE", code, message)


def _allocation_error(code, message):
    return ProductionPlanningError("ALLOCATION_CONFLICT", code, message)
