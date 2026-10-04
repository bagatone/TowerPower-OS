"""Caso d'uso CONSUMO_MATERIALI_SEMINA: 4 vaschette + 4 substrati per SET.

Pubblica due SCARICO ARTICOLO (unita' UNIT) tramite MovimentoArticoloService.
Prima di scrivere verifica semina e articoli. I due movimenti hanno key
idempotenti derivate da (semina, ruolo): se il secondo fallisse dopo il primo,
rilanciare lo stesso comando riproduce il primo (COMPATIBLE_REPLAY) e completa
il secondo, senza duplicare nulla.
"""
from __future__ import annotations

from ...domain.identifiers import ArticoloId
from ...domain.states import MovimentoType
from ..movimento_articolo.models import MovimentoArticoloAuthority, RegistraMovimentoArticolo
from ..movimento_articolo.service import MovimentoArticoloService
from decimal import Decimal
from .errors import (
    ConsumoMaterialiArticoloAmbiguousError,
    ConsumoMaterialiArticoloNotFoundError,
    ConsumoMaterialiSeminaNotFoundError,
    InvalidConsumoMaterialiCommandError,
)
from .models import (
    DENOMINAZIONE_SUBSTRATO_DEFAULT,
    DENOMINAZIONE_VASCHETTE_DEFAULT,
    RegistraConsumoMaterialiSemina,
    RegistraConsumoMaterialiSeminaResult,
)
from .ports import ConsumoMaterialiReader


class ConsumoMaterialiService:
    def __init__(self, reader: ConsumoMaterialiReader,
                 movimenti: MovimentoArticoloService) -> None:
        self._reader = reader
        self._movimenti = movimenti

    def _articolo(self, esplicito: ArticoloId | None, denominazione: str) -> ArticoloId:
        if esplicito is not None:
            if not self._reader.articolo_esiste(esplicito):
                raise ConsumoMaterialiArticoloNotFoundError(f"{esplicito.value} inesistente.")
            return esplicito
        trovati = self._reader.trova_articoli_per_denominazione(denominazione)
        if not trovati:
            raise ConsumoMaterialiArticoloNotFoundError(
                f"Nessun ARTICOLO chiamato '{denominazione}': registralo prima "
                "(articolo commissiona) oppure indicalo esplicitamente."
            )
        if len(trovati) > 1:
            raise ConsumoMaterialiArticoloAmbiguousError(
                f"Piu' ARTICOLI chiamati '{denominazione}': indica quello giusto esplicitamente."
            )
        return trovati[0]

    def registra(
        self, command: RegistraConsumoMaterialiSemina
    ) -> RegistraConsumoMaterialiSeminaResult:
        if not isinstance(command, RegistraConsumoMaterialiSemina):
            raise InvalidConsumoMaterialiCommandError("command non valido.")
        semina = self._reader.trova_semina(command.semina_id)
        if semina is None:
            raise ConsumoMaterialiSeminaNotFoundError(f"{command.semina_id.value} inesistente.")
        vaschette = self._articolo(command.articolo_vaschette, DENOMINAZIONE_VASCHETTE_DEFAULT)
        substrato = self._articolo(command.articolo_substrato, DENOMINAZIONE_SUBSTRATO_DEFAULT)
        if vaschette == substrato:
            raise InvalidConsumoMaterialiCommandError(
                "vaschette e substrato devono essere due ARTICOLI diversi."
            )
        effective_at = command.effective_at or semina.data_avvio
        pezzi = Decimal(command.pezzi)
        motivo = (
            f"Consumo semina {semina.semina_id.value} ({semina.codice_tracciabilita}, "
            f"{semina.varieta}): {command.set_seminati} SET x {command.pezzi_per_set} = {command.pezzi}"
        )
        risultati = []
        for ruolo, articolo in (("vaschette", vaschette), ("substrato", substrato)):
            risultati.append(self._movimenti.registra(RegistraMovimentoArticolo(
                articolo_id=articolo,
                tipo=MovimentoType.SCARICO,
                quantita=pezzi,
                unita_misura="UNIT",
                effective_at=effective_at,
                motivo=f"{motivo} {ruolo}",
                authority=MovimentoArticoloAuthority(
                    command.authority.actor,
                    command.authority.reason,
                    command.authority.correlation_id,
                    f"consumo-semina-{semina.semina_id.value}-{ruolo}",
                ),
            )))
        return RegistraConsumoMaterialiSeminaResult(
            semina.semina_id, semina.codice_tracciabilita, command.set_seminati,
            command.pezzi_per_set, risultati[0], risultati[1],
        )
