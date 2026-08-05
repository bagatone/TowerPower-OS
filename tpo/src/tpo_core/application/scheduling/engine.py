"""Scheduling Engine puro e deterministico."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from ...domain.entities.ordine import Ordine, RigaOrdine
from ...domain.entities.programma_fornitura import (
    ProgrammaFornitura,
    RigaProgrammaFornitura,
    TipoRicorrenza,
)
from ...domain.identifiers import OrdineId
from ...domain.states import OrdineState, ProgrammaFornituraState, RunState
from .models import (
    GeneratedOrderDraft,
    ScheduledOrderRecord,
    SchedulingRequest,
    SchedulingResult,
)
from .provenance import OrderLineProvenance, VersionedProgramLine, VersionedProgrammaFornitura


class SchedulingEngine:
    """Calcola gli ORDINI dovuti senza leggere orologi o repository."""

    def execute(self, request: SchedulingRequest) -> SchedulingResult:
        now = request.current_system_date
        existing_keys = {
            record.chiave_idempotenza for record in request.ordini_esistenti
        }
        drafts: list[GeneratedOrderDraft] = []
        righe_valutate = 0

        for versioned_programma in request.programmi:
            authoritative = isinstance(versioned_programma, VersionedProgrammaFornitura)
            programma = (
                versioned_programma.programma if authoritative else versioned_programma
            )
            if not self._elaborabile(programma, now.date):
                continue
            righe_valutate += len(programma.righe)
            gruppi = self._occorrenze_dovute(
                versioned_programma, now.date, now.time
            )
            for data_consegna, righe_programma in gruppi:
                righe_ordine = tuple(
                    RigaOrdine(
                        (locator.line if authoritative else locator).varieta_id,
                        (locator.line if authoritative else locator).quantita,
                    )
                    for locator in righe_programma
                )
                key = self._chiave_idempotenza(
                    programma, data_consegna, righe_ordine
                )
                drafts.append(
                    GeneratedOrderDraft(
                        cliente_id=programma.cliente_id,
                        programma_fornitura_id=programma.id,
                        data_ordine=now.date,
                        data_consegna_prevista=data_consegna,
                        righe=righe_ordine,
                        chiave_idempotenza=key,
                        provenance=tuple(
                            OrderLineProvenance(
                                programma_fornitura_id=programma.id,
                                programma_version=versioned_programma.version,
                                programma_line_position=locator.position,
                                order_line_position=order_position,
                            )
                            for order_position, locator in enumerate(
                                righe_programma, start=1
                            )
                        ) if authoritative else (),
                    )
                )

        nuovi_drafts = tuple(
            draft for draft in drafts if draft.chiave_idempotenza not in existing_keys
        )
        saltate = len(drafts) - len(nuovi_drafts)

        if request.simulation:
            records: tuple[ScheduledOrderRecord, ...] = ()
            anteprime = nuovi_drafts
        else:
            assert request.id_generator is not None
            records = tuple(
                self._genera_ordine(draft, request.id_generator)
                for draft in nuovi_drafts
            )
            anteprime = ()

        return SchedulingResult(
            run_id=request.run_id,
            ordini_generati=records,
            anteprime=anteprime,
            programmi_letti=len(request.programmi),
            righe_valutate=righe_valutate,
            occorrenze_valutate=len(drafts),
            occorrenze_generate=len(nuovi_drafts),
            occorrenze_saltate_per_idempotenza=saltate,
            avvisi=(),
            simulation=request.simulation,
            esito=RunState.SUCCESS,
        )

    @staticmethod
    def _elaborabile(programma: ProgrammaFornitura, current_date: date) -> bool:
        if programma.stato is not ProgrammaFornituraState.ATTIVO:
            return False
        if current_date < programma.data_inizio:
            return False
        return programma.data_fine is None or current_date <= programma.data_fine

    def _occorrenze_dovute(
        self,
        versioned_programma: VersionedProgrammaFornitura | ProgrammaFornitura,
        current_date: date,
        current_time,
    ) -> tuple[tuple[date, tuple[VersionedProgramLine | RigaProgrammaFornitura, ...]], ...]:
        authoritative = isinstance(versioned_programma, VersionedProgrammaFornitura)
        programma = versioned_programma.programma if authoritative else versioned_programma
        gruppi: dict[date, list[VersionedProgramLine | RigaProgrammaFornitura]] = defaultdict(list)
        ultimo_giorno = current_date + timedelta(
            days=programma.finestra_operativa_giorni
        )
        data_consegna = current_date
        while data_consegna <= ultimo_giorno:
            if data_consegna >= programma.data_inizio and (
                programma.data_fine is None or data_consegna <= programma.data_fine
            ):
                data_generazione = data_consegna - timedelta(
                    days=programma.finestra_operativa_giorni
                )
                orario_raggiunto = (
                    data_generazione < current_date
                    or current_time.replace(tzinfo=None) >= programma.orario_generazione
                )
                if data_generazione <= current_date and orario_raggiunto:
                    sources = versioned_programma.lines if authoritative else programma.righe
                    for locator in sources:
                        line = locator.line if authoritative else locator
                        if self._ricorre(line, programma.data_inizio, data_consegna):
                            gruppi[data_consegna].append(locator)
            data_consegna += timedelta(days=1)
        return tuple((giorno, tuple(righe)) for giorno, righe in sorted(gruppi.items()))

    @staticmethod
    def _ricorre(
        riga: RigaProgrammaFornitura,
        ancora: date,
        data_consegna: date,
    ) -> bool:
        config = riga.configurazione_temporale
        giorni = (data_consegna - ancora).days
        if giorni < 0:
            return False
        if config.tipo is TipoRicorrenza.SETTIMANALE:
            return giorni % 7 == 0
        if config.tipo is TipoRicorrenza.QUINDICINALE:
            return giorni % 15 == 0
        if config.tipo is TipoRicorrenza.MENSILE:
            return data_consegna.day == ancora.day
        if config.tipo is TipoRicorrenza.OGNI_X_GIORNI:
            assert config.intervallo_giorni is not None
            return giorni % config.intervallo_giorni == 0
        return data_consegna.isoweekday() in config.giorni_settimana

    @staticmethod
    def _decimal_canonico(value: Decimal) -> str:
        return format(value.normalize(), "f")

    @classmethod
    def _chiave_idempotenza(
        cls,
        programma: ProgrammaFornitura,
        data_consegna: date,
        righe: tuple[RigaOrdine, ...],
    ) -> str:
        righe_canoniche = sorted(
            righe,
            key=lambda riga: (
                riga.varieta_id.value,
                riga.quantita.unit.value,
                cls._decimal_canonico(riga.quantita.value),
            ),
        )
        payload = {
            "programma_fornitura_id": programma.id.value,
            "cliente_id": programma.cliente_id.value,
            "data_consegna_prevista": data_consegna.isoformat(),
            "righe": [
                {
                    "varieta_id": riga.varieta_id.value,
                    "quantita": cls._decimal_canonico(riga.quantita.value),
                    "unita": riga.quantita.unit.value,
                }
                for riga in righe_canoniche
            ],
        }
        canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _genera_ordine(draft: GeneratedOrderDraft, id_generator) -> ScheduledOrderRecord:
        ordine = Ordine(
            id=id_generator.next_id(OrdineId),
            cliente_id=draft.cliente_id,
            data_ordine=draft.data_ordine,
            righe=draft.righe,
            stato=OrdineState.APERTO,
            programma_fornitura_id=draft.programma_fornitura_id,
        )
        return ScheduledOrderRecord(
            ordine=ordine,
            data_consegna_prevista=draft.data_consegna_prevista,
            chiave_idempotenza=draft.chiave_idempotenza,
            provenance=draft.provenance,
        )
