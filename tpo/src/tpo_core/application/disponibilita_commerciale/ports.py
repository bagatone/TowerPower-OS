"""Porta del reader a sola lettura DISPONIBILITA_COMMERCIALE."""

from typing import Protocol

from .models import DisponibilitaCommerciale, RichiediDisponibilitaCommerciale


class DisponibilitaCommercialeReader(Protocol):
    def disponibilita(
        self, query: RichiediDisponibilitaCommerciale
    ) -> DisponibilitaCommerciale:
        """Calcola DISPONIBILE/PRENOTATO/VENDIBILE per una VARIETA. Sola
        lettura: non scrive mai su tpo.stock."""
        ...
