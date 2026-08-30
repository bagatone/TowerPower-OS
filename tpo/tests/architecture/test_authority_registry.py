import re
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[2]
REGISTRY_PATH = ROOT / "docs/architecture/AUTHORITY_REGISTRY.yaml"
IDENTIFIERS_PATH = ROOT / "src/tpo_core/domain/identifiers.py"

REQUIRED_FIELDS = {
    "concept_id", "canonical_name", "domain", "classification", "status",
    "current_authorities", "core_implementations", "persistence_authorities",
    "identities", "legacy_predecessors", "preserved_rules",
    "explicitly_superseded_rules", "forbidden_duplicates", "conflicts",
    "open_owner_decisions", "correction_semantics", "audit_authority",
    "idempotency_authority", "verification_tests", "reviewed_at_commit",
}
UNRESOLVED = "UNKNOWN / OWNER DECISION REQUIRED"
EXPECTED_VARIETY_CODES = {
    "AFI": "Afila / Guisantes",
    "RAB": "Rábano Morado",
    "CIL": "Cilantro",
    "MIZ": "Mizuna Roja",
    "HIN": "Hinojo",
    "ALB": "Albahaca",
    "GIR": "Girasol",
    "COL": "Col Roja",
    "MOS": "Mostaza",
    "LEN": "Lentejas",
    "PAK": "Pak Choi",
    "RUC": "Rúcula",
    "AMA": "Amaranto Rojo",
    "ACE": "Acedera / Vinagrera",
}


def _registry():
    parsed = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    assert parsed["schema_version"] == 1
    assert isinstance(parsed["concepts"], list) and parsed["concepts"]
    return parsed


def test_registry_parses_and_has_unique_complete_concepts():
    concepts = _registry()["concepts"]
    concept_ids = [item["concept_id"] for item in concepts]
    assert len(concept_ids) == len(set(concept_ids))
    assert all(REQUIRED_FIELDS <= item.keys() for item in concepts)


def test_forbidden_duplicate_aliases_are_unique():
    aliases = [
        guard["alias"]
        for concept in _registry()["concepts"]
        for guard in concept["forbidden_duplicates"]
    ]
    assert len(aliases) == len(set(aliases))


def test_owner_approved_variety_traceability_code_master_is_exact_and_guarded():
    master = _registry()["variety_traceability_code_master"]
    mappings = {
        item["code"]: item["variety"] for item in master["canonical_codes"]
    }
    assert master["status"] == "OWNER_APPROVED"
    assert master["code_format"] == "^[A-Z]{3}$"
    assert mappings == EXPECTED_VARIETY_CODES
    assert len(mappings) == len(master["canonical_codes"]) == 14
    assert all(re.fullmatch(r"[A-Z]{3}", code) for code in mappings)
    forbidden = {
        item["code"]: item for item in master["forbidden_new_production_codes"]
    }
    assert forbidden["BAS"]["canonical_replacement"] == "ALB"
    assert forbidden["VIN"]["canonical_replacement"] == "ACE"
    assert master["permanently_reserved_outside_production"] == ["MOS"]
    assert master["explicitly_not_authorized_or_reserved"] == [
        {"code": "BAR", "name": "Barilla"}
    ]


def test_owner_approved_raccolta_authority_is_exact_and_fail_closed():
    authority = _registry()["raccolta_authority_v1"]
    assert authority["status"] == "OWNER_APPROVED"
    assert authority["prior_art_gate"] == "PASSED"
    assert authority["identity"] == {
        "type": "RaccoltaId", "format": "^RAC-[0-9]{6,}$",
        "prefix": "RAC", "sequence": "RACCOLTA_ID",
    }
    assert authority["eligible_semina_states"] == ["PRONTA_ALLA_RACCOLTA"]
    assert authority["automatic_semina_transition"] == "FORBIDDEN"
    assert authority["automatic_semina_closure"] == "FORBIDDEN"
    assert authority["mutability"] == {"update": "FORBIDDEN", "delete": "FORBIDDEN"}
    assert authority["traceability"]["authoritative_raccolta_snapshot"] == "FORBIDDEN"
    assert authority["traceability"]["second_production_lot"] == "FORBIDDEN"
    assert authority["stock_boundary"] == {
        "direct_stock_mutation": "FORBIDDEN", "automatic_movement": "FORBIDDEN",
    }
    assert authority["destination_as_assignment"] == "FORBIDDEN"
    assert authority["quality_authority"] == "DEFERRED"
    assert authority["correction_implementation"] == "DEFERRED"


def test_raccolta_registry_entry_has_no_unresolved_authority():
    raccolta = next(
        item for item in _registry()["concepts"] if item["concept_id"] == "RACCOLTA"
    )
    assert raccolta["identities"] == [
        {"type": "RaccoltaId", "prefix": "RAC", "sequence": "RACCOLTA_ID"}
    ]
    assert raccolta["conflicts"] == []
    assert raccolta["open_owner_decisions"] == []
    assert raccolta["audit_authority"] == "tpo.audit_eventi"
    assert raccolta["idempotency_authority"] == "tpo.raccolta_recording_requests"


def test_raccolta_freeze_preserves_all_owner_guards():
    freeze = (
        ROOT / "docs/architecture/RACCOLTA_AUTHORITY_FREEZE.md"
    ).read_text(encoding="utf-8")
    required = (
        "PRIOR ART REVIEW PASSED", "RAC-[0-9]{6,}", "RACCOLTA_ID",
        "PRONTA_ALLA_RACCOLTA", "UPDATE = FORBIDDEN", "DELETE = FORBIDDEN",
        "COMPATIBLE_REPLAY", "tpo.raccolta_recording_requests",
        "Atlantic/Canary", "numeric(20,6)", "0.5 SET", "LOTTO_PRODUZIONE",
        "QUALITY AUTHORITY = DEFERRED", "non modifica STOCK",
        "MOVIMENTO_MAGAZZINO nascosto", "non è ASSEGNAZIONE",
        "correction/reversal/void",
    )
    assert all(value in freeze for value in required)


def test_owner_approved_semente_authority_is_exact_and_fail_closed():
    authority = _registry()["semente_authority_v1"]
    assert authority["status"] == "OWNER_APPROVED"
    assert authority["prior_art_gate"] == "PASSED"
    assert authority["identity"] == {
        "public_identity": "NONE", "public_sequence": "NONE",
        "technical_persistence_identity": "internal bigint tpo.sementi.id",
    }
    assert authority["business_identity"]["fields"] == ["fornitore", "referenza_commerciale"]
    assert authority["mutability"]["fornitore"] == "FORBIDDEN"
    assert authority["mutability"]["referenza_commerciale"] == "FORBIDDEN"
    assert authority["semente_impiego_relationship"]["automatic_creation"] == "FORBIDDEN"
    assert authority["semente_impiego_relationship"]["required_for_semente_creation"] is False
    assert authority["semente_impiego_relationship"]["required_for_lotto_seme_creation"] is False
    assert authority["semente_impiego_relationship"]["required_for_semina_commissioning"] is True
    assert authority["articolo_coupling"] == "DEFERRED"
    assert authority["fornitore_master_authority"] == "NONE"


def test_semente_registry_entry_has_no_unresolved_authority():
    semente = next(
        item for item in _registry()["concepts"] if item["concept_id"] == "SEMENTE"
    )
    assert semente["identities"] == []
    assert semente["conflicts"] == []
    assert semente["open_owner_decisions"] == []
    assert semente["audit_authority"] == "tpo.audit_eventi"
    cultivar = next(
        item for item in _registry()["concepts"] if item["concept_id"] == "CULTIVAR"
    )
    assert cultivar["identities"] == [
        {"type": "ProtocolloVersioneId", "prefix": "PV", "sequence": "PROTOCOLLO_VERSIONE_ID"}
    ]


def test_semente_freeze_preserves_all_owner_guards():
    freeze = (
        ROOT / "docs/architecture/SEMENTE_AUTHORITY_FREEZE.md"
    ).read_text(encoding="utf-8")
    required = (
        "PRIOR ART REVIEW PASSED",
        "public identity | `NONE`",
        "public sequence | `NONE`",
        "lower(btrim(fornitore))",
        "lower(btrim(referenza_commerciale))",
        "uq_sementi_fornitore_referenza_normalized",
        "fornitore              = FORBIDDEN to mutate",
        "referenza_commerciale  = FORBIDDEN to mutate",
        "COMPATIBLE_REPLAY",
        "tpo.semente_commissioning_requests",
        "SEMENTE_IMPIEGO",
        "ARTICOLO",
        "LOTTO_SEME",
        "SEM-CIL",
    )
    assert all(value in freeze for value in required)


def test_every_current_core_public_identity_prefix_is_registered():
    source = IDENTIFIERS_PATH.read_text(encoding="utf-8")
    core_prefixes = set(re.findall(r'prefix: ClassVar\[str\] = "([A-Z]+)"', source))
    registered = {
        identity["prefix"]
        for concept in _registry()["concepts"]
        for identity in concept["identities"]
    }
    assert core_prefixes <= registered


def test_every_registered_architecture_freeze_exists():
    freezes = [
        authority["path"]
        for concept in _registry()["concepts"]
        for authority in concept["current_authorities"]
        if authority["kind"] == "architecture_freeze"
    ]
    assert freezes
    assert all((ROOT / path).is_file() for path in freezes)


def test_superseded_status_requires_a_replacement_or_decision_reference():
    for concept in _registry()["concepts"]:
        if concept["status"] in {
            "SUPERSEDED EXPLICITLY", "OBSOLETE WITH EXPLICIT REPLACEMENT"
        }:
            assert concept.get("replacement_or_decision_reference")


def test_unresolved_concepts_remain_explicit_and_have_owner_decisions():
    unresolved = [item for item in _registry()["concepts"] if item["status"] == UNRESOLVED]
    assert unresolved
    assert all(item["open_owner_decisions"] for item in unresolved)
    required_unresolved = {
        "PRODOTTO", "ARTICOLO", "ASSEGNAZIONE_FISICA", "FATTURA",
        "INCASSO_PAGAMENTO", "HYDRATION_RULES",
    }
    assert required_unresolved <= {item["concept_id"] for item in unresolved}


def test_governance_freeze_is_fail_closed_and_reconciles_harvest_suspension():
    freeze = (ROOT / _registry()["normative_governance"]).read_text(encoding="utf-8")
    required = (
        "PostgreSQL Core is the current operational runtime authority",
        "Legacy Google documents and code may contain preserved domain knowledge",
        "PRIOR ART REVIEW PASSED", "PRIOR ART REVIEW BLOCKED", "fail-closed",
        "former suspension",
        "RACCOLTA_AUTHORITY_FREEZE.md",
        "Harvest design resumes only within",
        "OWNER / ARCHITECTURE DECISION REQUIRED",
    )
    assert all(value in freeze for value in required)


def test_semina_traceability_freeze_reconciles_only_the_authorized_scope():
    freeze = (
        ROOT / "docs/architecture/SEMINA_TRACEABILITY_CODE_AUTHORITY_FREEZE.md"
    ).read_text(encoding="utf-8")
    required = (
        "PRIOR ART REVIEW PASSED",
        "one SEM-* <-> exactly one AAA-GGMM-L",
        "^[A-Z]{3}-[0-9]{4}-[A-Z]$",
        "VARIETA Configuration",
        "Atlantic/Canary",
        "A, B, C, ... Z",
        "OBSOLETE WITH EXPLICIT REPLACEMENT",
        "PREDB is never generated for new production",
        "`SEM-CIL` does not satisfy `SEM-[0-9]{6,}`",
        "No `LOTTO_PRODUZIONE` aggregate",
        "does not implement RACCOLTA, STOCK, CONSEGNA or FATTURA",
    )
    assert all(value in freeze for value in required)
