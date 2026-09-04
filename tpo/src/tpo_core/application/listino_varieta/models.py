"""Immutable command and outcome for governed LISTINO_VARIETA price configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from ...domain.identifiers import ActorId, VarietaId
from .errors import InvalidListinoVarietaCommandError


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidListinoVarietaCommandError(f"{name} deve essere testo normalizzato non vuoto.")


@dataclass(frozen=True)
class ListinoVarietaAuthority:
    actor: ActorId
    reason: str
    correlation_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorId):
            raise InvalidListinoVarietaCommandError("actor non valido.")
        _text("reason", self.reason)
        _text("correlation_id", self.correlation_id)


@dataclass(frozen=True)
class ImpostaPrezzoListinoVarieta:
    varieta_id: VarietaId
    prezzo_unitario: Decimal
    aliquota_igic: Decimal
    authority: ListinoVarietaAuthority

    def __post_init__(self) -> None:
        if not isinstance(self.varieta_id, VarietaId):
            raise InvalidListinoVarietaCommandError("varieta_id non valido.")
        if not isinstance(self.prezzo_unitario, Decimal):
            raise InvalidListinoVarietaCommandError("prezzo_unitario deve essere un Decimal.")
        if self.prezzo_unitario < 0:
            raise InvalidListinoVarietaCommandError("prezzo_unitario non può essere negativo.")
        if not isinstance(self.aliquota_igic, Decimal):
            raise InvalidListinoVarietaCommandError("aliquota_igic deve essere un Decimal.")
        if self.aliquota_igic < 0 or self.aliquota_igic > 100:
            raise InvalidListinoVarietaCommandError("aliquota_igic deve essere compresa tra 0 e 100.")
        if not isinstance(self.authority, ListinoVarietaAuthority):
            raise InvalidListinoVarietaCommandError("authority non valida.")


@dataclass(frozen=True)
class ImpostaPrezzoListinoVarietaResult:
    varieta_public_id: str
    prezzo_unitario: Decimal
    aliquota_igic: Decimal
    recorded_at: datetime
    inserted: bool
    updated: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.inserted, bool) or not isinstance(self.updated, bool):
            raise InvalidListinoVarietaCommandError("Esito ImpostaPrezzoListinoVarieta non valido.")
        if self.inserted == self.updated:
            raise InvalidListinoVarietaCommandError(
                "Esito ImpostaPrezzoListinoVarieta deve essere INSERTED oppure UPDATED, "
                "non entrambi o nessuno dei due."
            )

    @property
    def outcome(self) -> str:
        return "INSERTED" if self.inserted else "UPDATED"
