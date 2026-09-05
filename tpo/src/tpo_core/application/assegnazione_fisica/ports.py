"""Porta dell'unico writer ASSEGNAZIONE_FISICA."""

from typing import Protocol

from .models import RegistraAssegnazioneFisica, RegistraAssegnazioneFisicaResult


class AssegnazioneFisicaWriter(Protocol):
    def registra(
        self, command: RegistraAssegnazioneFisica
    ) -> RegistraAssegnazioneFisicaResult:
        """Registra una Fact di ASSEGNAZIONE_FISICA (RACCOLTA <-> RIGA_ORDINE,
        CONSEGNA opzionale) nel medesimo commit di allocazione identità e
        audit."""
        ...
