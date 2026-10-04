"""Porta di lettura per CONSUMO_MATERIALI_SEMINA (nessuna scrittura)."""

from typing import Protocol

from ...domain.identifiers import ArticoloId, SeminaId
from .models import SeminaPerConsumo


class ConsumoMaterialiReader(Protocol):
    def trova_semina(self, semina_id: SeminaId) -> SeminaPerConsumo | None:
        ...

    def trova_articoli_per_denominazione(self, denominazione: str) -> list[ArticoloId]:
        """Articoli con denominazione esatta (confronto case-insensitive)."""
        ...

    def articolo_esiste(self, articolo_id: ArticoloId) -> bool:
        ...
