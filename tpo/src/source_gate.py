from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable


SOURCE_NOT_AVAILABLE = "SOURCE_NOT_AVAILABLE"
DEFAULT_ALLOWED_DOCUMENT_SOURCES = {"GITHUB", "LOCAL", "OPERATING_RULES"}
DEFAULT_ALLOWED_SHEET_SOURCES = {"GOOGLE_SHEETS"}
OFFICIAL_SHEET_SOURCE = "GOOGLE_SHEETS"

REQUEST_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "clienti": ("CLIENTI",),
    "consegne": ("CONSEGNE",),
    "lotti": ("LOTTI",),
    "semine": ("SEMINE",),
    "raccolti": ("RACCOLTI",),
    "stock": ("STOCK",),
    "piano_semine": ("PIANO_SEMINE",),
    "calendario_produzione": ("CALENDARIO_PRODUZIONE",),
    "pianificazione": (
        "PIANO_SEMINE",
        "CALENDARIO_PRODUZIONE",
        "MASTER_VARIETA",
        "CONSEGNE",
        "STOCK",
    ),
    "aggiornami": (
        "CONSEGNE",
        "STOCK",
        "LOTTI",
        "SEMINE",
        "RACCOLTI",
        "PROBLEMI",
        "MASTER_VARIETA",
        "PIANO_SEMINE",
        "CALENDARIO_PRODUZIONE",
        "BRIEFING_GIORNALIERO",
    ),
    "briefing_giornaliero": (
        "CONSEGNE",
        "STOCK",
        "LOTTI",
        "SEMINE",
        "RACCOLTI",
        "PROBLEMI",
        "MASTER_VARIETA",
        "PIANO_SEMINE",
        "CALENDARIO_PRODUZIONE",
        "BRIEFING_GIORNALIERO",
    ),
    "event_semina": (
        "MASTER_VARIETA",
        "SEMINE",
        "LOTTI",
        "INVENTARIO",
        "RICETTE_PRODUZIONE",
        "MOVIMENTI_MAGAZZINO",
    ),
    "event_ordine_ricorrente": (
        "CLIENTI",
        "CONSEGNE",
        "MASTER_VARIETA",
        "PIANO_SEMINE",
        "CALENDARIO_PRODUZIONE",
        "STOCK",
        "INVENTARIO",
        "RICETTE_PRODUZIONE",
    ),
}


class SourceGateError(RuntimeError):
    pass


class SourceNotAvailableError(SourceGateError):
    def __init__(self, missing_sources: list[str]) -> None:
        self.status = SOURCE_NOT_AVAILABLE
        self.missing_sources = missing_sources
        super().__init__(
            f"{SOURCE_NOT_AVAILABLE}: fonti mancanti o non lette: "
            f"{', '.join(missing_sources)}"
        )


@dataclass(frozen=True)
class SourceRequirement:
    source_type: str
    source_name: str
    sheet_name: str = ""
    required: bool = True

    @classmethod
    def google_sheet(cls, sheet_name: str) -> "SourceRequirement":
        return cls(
            source_type=OFFICIAL_SHEET_SOURCE,
            source_name=sheet_name,
            sheet_name=sheet_name,
        )

    @property
    def key(self) -> str:
        return _source_key(self.source_type, self.source_name)


@dataclass(frozen=True)
class SourceProvenance:
    source_type: str
    source_name: str
    loaded_at: str
    read_successfully: bool
    freshness_timestamp: str = ""
    sheet_name: str = ""
    locator: str = ""
    reference: str = ""
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def source(self) -> str:
        return self.source_type.lower()

    @property
    def name(self) -> str:
        return self.source_name

    @property
    def kind(self) -> str:
        return "sheet" if self.sheet_name else "document"


@dataclass(frozen=True)
class SourceGateResult:
    status: str
    requirements: list[SourceRequirement] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=list)
    provenance: list[SourceProvenance] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.status == "OK"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "missing_sources": self.missing_sources,
            "provenance": [item.to_dict() for item in self.provenance],
        }


class SourceGate:
    def __init__(
        self,
        enabled: bool = True,
        allowed_document_sources: Iterable[str] | None = None,
        allowed_sheet_sources: Iterable[str] | None = None,
        require_checksum: bool = False,
    ) -> None:
        self.enabled = enabled
        self.allowed_document_sources = _normalize_sources(
            allowed_document_sources,
            DEFAULT_ALLOWED_DOCUMENT_SOURCES,
        )
        self.allowed_sheet_sources = _normalize_sources(
            allowed_sheet_sources,
            DEFAULT_ALLOWED_SHEET_SOURCES,
        )
        self.require_checksum = require_checksum

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "SourceGate":
        source_gate_config = config.get("source_gate", {})
        return cls(
            enabled=source_gate_config.get("enabled", True),
            allowed_document_sources=source_gate_config.get("allowed_document_sources"),
            allowed_sheet_sources=source_gate_config.get("allowed_sheet_sources"),
            require_checksum=source_gate_config.get("require_checksum", False),
        )

    def requirements_for(self, request_type: str) -> list[SourceRequirement]:
        normalized = str(request_type).strip().lower()
        if normalized not in REQUEST_REQUIREMENTS:
            raise SourceGateError(f"Tipo richiesta Source Gate non supportato: {request_type}")
        return [
            SourceRequirement.google_sheet(sheet_name)
            for sheet_name in REQUEST_REQUIREMENTS[normalized]
        ]

    def check_request(
        self,
        request_type: str,
        loaded_sources: dict[str, Any],
    ) -> SourceGateResult:
        requirements = self.requirements_for(request_type)
        if not self.enabled:
            return SourceGateResult(
                status="OK",
                requirements=requirements,
                provenance=self._collect_provenance(requirements, loaded_sources),
            )

        missing_sources: list[str] = []
        provenance: list[SourceProvenance] = []
        for requirement in requirements:
            item = loaded_sources.get(requirement.source_name)
            item_provenance = getattr(item, "provenance", None)
            if not item or not item_provenance:
                missing_sources.append(requirement.source_name)
                continue
            if not self._is_allowed(item_provenance):
                missing_sources.append(requirement.source_name)
                continue
            if not item_provenance.read_successfully:
                missing_sources.append(requirement.source_name)
                continue
            if self.require_checksum and not item_provenance.checksum:
                missing_sources.append(requirement.source_name)
                continue
            provenance.append(item_provenance)

        if missing_sources:
            return SourceGateResult(
                status=SOURCE_NOT_AVAILABLE,
                requirements=requirements,
                missing_sources=missing_sources,
                provenance=provenance,
            )

        return SourceGateResult(
            status="OK",
            requirements=requirements,
            provenance=provenance,
        )

    def enforce_request(
        self,
        request_type: str,
        loaded_sources: dict[str, Any],
    ) -> SourceGateResult:
        result = self.check_request(request_type, loaded_sources)
        if not result.allowed:
            raise SourceNotAvailableError(result.missing_sources)
        return result

    def assert_documents(self, documents: dict[str, Any]) -> None:
        self._assert_provenance(
            items=documents.values(),
            allowed_sources=self.allowed_document_sources,
            expected_sheet=False,
        )

    def assert_sheets(self, sheets: dict[str, Any]) -> None:
        self._assert_provenance(
            items=sheets.values(),
            allowed_sources=self.allowed_sheet_sources,
            expected_sheet=True,
        )

    def _assert_provenance(
        self,
        items: Iterable[Any],
        allowed_sources: set[str],
        expected_sheet: bool,
    ) -> None:
        if not self.enabled:
            return

        errors: list[str] = []
        for item in items:
            provenance = getattr(item, "provenance", None)
            item_name = getattr(item, "name", "fonte")
            if provenance is None:
                errors.append(f"{item_name}: provenance mancante.")
                continue
            if _normalize_source(provenance.source_type) not in allowed_sources:
                errors.append(f"{item_name}: sorgente non autorizzata ({provenance.source_type}).")
            if expected_sheet and not provenance.sheet_name:
                errors.append(f"{item_name}: sheet_name mancante.")
            if not expected_sheet and provenance.sheet_name:
                errors.append(f"{item_name}: tipo sorgente non valido.")
            if not provenance.read_successfully:
                errors.append(f"{item_name}: fonte non letta.")
            if self.require_checksum and not provenance.checksum:
                errors.append(f"{item_name}: checksum mancante.")

        if errors:
            raise SourceGateError("Source Gate bloccato:\n" + "\n".join(errors))

    def _collect_provenance(
        self,
        requirements: list[SourceRequirement],
        loaded_sources: dict[str, Any],
    ) -> list[SourceProvenance]:
        provenance: list[SourceProvenance] = []
        for requirement in requirements:
            item = loaded_sources.get(requirement.source_name)
            item_provenance = getattr(item, "provenance", None)
            if item_provenance:
                provenance.append(item_provenance)
        return provenance

    def _is_allowed(self, provenance: SourceProvenance) -> bool:
        source_type = _normalize_source(provenance.source_type)
        if provenance.sheet_name:
            return source_type in self.allowed_sheet_sources
        return source_type in self.allowed_document_sources


def build_content_checksum(content: str | bytes | list[list[str]]) -> str:
    if isinstance(content, bytes):
        payload = content
    elif isinstance(content, str):
        payload = content.encode("utf-8")
    else:
        payload = json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_google_sheets_provenance(
    sheet_name: str,
    spreadsheet_id: str,
    values: list[list[str]],
    read_successfully: bool = True,
) -> SourceProvenance:
    return SourceProvenance(
        source_type=OFFICIAL_SHEET_SOURCE,
        source_name=sheet_name,
        loaded_at=current_timestamp(),
        read_successfully=read_successfully,
        sheet_name=sheet_name,
        locator=f"{spreadsheet_id}:{sheet_name}!A:ZZ",
        reference=spreadsheet_id,
        checksum=build_content_checksum(values),
    )


def provenance_report(items: dict[str, Any]) -> dict[str, dict[str, Any]]:
    report: dict[str, dict[str, Any]] = {}
    for name, item in items.items():
        provenance = getattr(item, "provenance", None)
        if provenance is not None:
            report[name] = provenance.to_dict()
    return report


def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_key(source_type: str, source_name: str) -> str:
    return f"{_normalize_source(source_type)}:{str(source_name).strip().upper()}"


def _normalize_sources(
    sources: Iterable[str] | None,
    default_sources: set[str],
) -> set[str]:
    values = sources if sources is not None else default_sources
    return {_normalize_source(source) for source in values if str(source).strip()}


def _normalize_source(source: str) -> str:
    return str(source).strip().upper()
