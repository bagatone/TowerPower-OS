"""Istanze valide dei modelli applicativi, usate come dati finti nei test
del web adapter (nessuna connessione reale: i servizi applicativi sono
usati con reader finti in-memory, iniettati via dependency override)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from src.tpo_core.application.clienti_lettura.models import Cliente
from src.tpo_core.application.disponibilita_commerciale.models import DisponibilitaCommerciale
from src.tpo_core.application.finanze_lettura.models import Fattura, Incasso, RigaFattura, Uscita
from src.tpo_core.application.fornitura_ordini_consegne_lettura.models import (
    AssegnazioneFisica, Consegna, Ordine, ProgrammaFornitura, RigaConsegna, RigaOrdine,
    RigaProgrammaFornitura,
)
from src.tpo_core.application.magazzino_lettura.models import (
    Articolo, MovimentoMagazzino, StockArticolo, StockVarieta,
)
from src.tpo_core.application.run_lettura.models import Run, RunLog, RunLogVoce, RunMessaggio
from src.tpo_core.application.semente_lettura.models import LottoSeme, Semente
from src.tpo_core.application.semina_raccolta_lettura.models import Raccolta, Semina
from src.tpo_core.application.varieta_lettura.models import Varieta
from src.tpo_core.domain.identifiers import (
    ArticoloId, AssegnazioneFisicaId, ClienteId, ConsegnaId, IncassoId, LottoSemeId,
    MovimentoId, NumeroFattura, OrdineId, ProgrammaFornituraId, RaccoltaId, RunId,
    SeminaId, UscitaId, VarietaId,
)

UTC = timezone.utc


def cliente() -> Cliente:
    return Cliente(
        cliente_id=ClienteId("CLI-000001"),
        denominazione="Abaluus",
        modalita_fatturazione="PERIODICA_MENSILE",
        termini_pagamento_giorni=30,
        created_at=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
        updated_at=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
    )


def varieta() -> Varieta:
    return Varieta(
        varieta_id=VarietaId("VAR-000002"),
        denominazione="Rábano",
        stato="ATTIVA",
        prezzo_unitario=Decimal("12.50"),
        aliquota_igic=Decimal("7"),
        created_at=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
        updated_at=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
    )


def disponibilita() -> DisponibilitaCommerciale:
    return DisponibilitaCommerciale(
        varieta_id=VarietaId("VAR-000002"),
        unita_misura="GRAM",
        disponibile=Decimal("100"),
        prenotato=Decimal("40"),
        vendibile=Decimal("60"),
        integrita_allarme=False,
    )


def semente() -> Semente:
    return Semente(
        semente_id=19,
        fornitore="Hyfarm",
        referenza_commerciale="Rabano (Radish) - Hyfarm",
        marca=None,
        trattamento=None,
        attiva=True,
    )


def lotto_seme() -> LottoSeme:
    return LottoSeme(
        lotto_seme_id=LottoSemeId("LSE-000019"),
        semente_fornitore="Hyfarm",
        semente_referenza_commerciale="Rabano (Radish) - Hyfarm",
        numero_lotto_produttore="L2026-01",
        data_ricezione=date(2026, 8, 1),
        data_scadenza=date(2027, 8, 1),
        quantita_iniziale=Decimal("500"),
        quantita_residua=Decimal("452"),
        unita_misura="GRAM",
        anomalia=None,
    )


def raccolta(semina_id: SeminaId) -> Raccolta:
    return Raccolta(
        raccolta_id=RaccoltaId("RAC-000001"),
        semina_id=semina_id,
        data_raccolta=datetime(2026, 9, 20, 7, 0, tzinfo=UTC),
        quantita=Decimal("12"),
        unita_misura="SET",
        operatore="Giulia",
        destinazione_prevista=None,
        note=None,
    )


def semina() -> Semina:
    semina_id = SeminaId("SEM-000001")
    return Semina(
        semina_id=semina_id,
        varieta_id=VarietaId("VAR-000002"),
        varieta_denominazione="Rábano",
        stato="GERMINAZIONE",
        quantita_seme=Decimal("48"),
        unita_misura="GRAM",
        data_avvio=datetime(2026, 9, 7, 8, 0, tzinfo=UTC),
        causa_origine="ORDINE_CLIENTE",
        esito_finale=None,
        cultivar_snapshot="Rábano",
        lotto_seme_snapshot="LSE-000019",
        raccolte=(raccolta(semina_id),),
    )


def articolo() -> Articolo:
    return Articolo(
        articolo_id=ArticoloId("ART-000001"),
        denominazione="Substrato fibra di cocco",
        unita_misura="KG",
        created_at=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
    )


def stock_varieta() -> StockVarieta:
    return StockVarieta(
        varieta_id=VarietaId("VAR-000002"),
        varieta_denominazione="Rábano",
        disponibile=Decimal("100"),
        unita_misura="GRAM",
        updated_at=datetime(2026, 9, 7, 8, 0, tzinfo=UTC),
        version=3,
    )


def stock_articolo() -> StockArticolo:
    return StockArticolo(
        articolo_id=ArticoloId("ART-000001"),
        articolo_denominazione="Substrato fibra di cocco",
        disponibile=Decimal("50"),
        unita_misura="KG",
        updated_at=datetime(2026, 9, 7, 8, 0, tzinfo=UTC),
        version=1,
    )


def movimento() -> MovimentoMagazzino:
    return MovimentoMagazzino(
        movimento_id=MovimentoId("MOV-000001"),
        varieta_id=VarietaId("VAR-000002"),
        varieta_denominazione="Rábano",
        articolo_id=None,
        articolo_denominazione=None,
        unita_misura="GRAM",
        tipo="CARICO",
        direzione="POSITIVO",
        quantita=Decimal("48"),
        data_movimento=datetime(2026, 9, 7, 8, 0, tzinfo=UTC),
        motivo="Commissioning SEMINA",
        origine_tipo="SEMINA",
        origine_riferimento="SEM-000001",
        raccolta_id=None,
        consegna_id=None,
        run_id=None,
        created_at=datetime(2026, 9, 7, 8, 0, tzinfo=UTC),
    )


def programma_fornitura() -> ProgrammaFornitura:
    return ProgrammaFornitura(
        programma_id=ProgrammaFornituraId("PF-000001"),
        cliente_id=ClienteId("CLI-000001"),
        cliente_denominazione="Abaluus",
        numero_versione=2,
        stato="ATTIVO",
        data_inizio=date(2026, 1, 1),
        data_fine=None,
        finestra_operativa_giorni=2,
        valida_dal=datetime(2026, 9, 1, tzinfo=UTC),
        righe=(
            RigaProgrammaFornitura(
                posizione=1,
                varieta_id=VarietaId("VAR-000002"),
                varieta_denominazione="Rábano",
                quantita=Decimal("2"),
                unita_misura="SET",
                tipo_ricorrenza="SETTIMANALE",
                intervallo_giorni=None,
                giorni_settimana=(1,),
            ),
        ),
    )


def ordine() -> Ordine:
    return Ordine(
        ordine_id=OrdineId("ORD-000001"),
        cliente_id=ClienteId("CLI-000001"),
        cliente_denominazione="Abaluus",
        programma_fornitura_id=ProgrammaFornituraId("PF-000001"),
        data_ordine=date(2026, 9, 1),
        data_consegna_prevista=date(2026, 9, 8),
        stato="APERTO",
        tipo_creazione="AUTOMATICO",
        righe=(
            RigaOrdine(
                posizione=1,
                varieta_id=VarietaId("VAR-000002"),
                varieta_denominazione="Rábano",
                quantita=Decimal("2"),
                unita_misura="SET",
            ),
        ),
    )


def consegna() -> Consegna:
    return Consegna(
        consegna_id=ConsegnaId("CON-000001"),
        cliente_id=ClienteId("CLI-000001"),
        cliente_denominazione="Abaluus",
        stato="PROGRAMMATA",
        data_prevista=date(2026, 9, 8),
        data_effettiva=None,
        destinazione_fisica=None,
        ordini_collegati=(OrdineId("ORD-000001"),),
        righe=(
            RigaConsegna(
                posizione=1,
                varieta_id=VarietaId("VAR-000002"),
                varieta_denominazione="Rábano",
                quantita=Decimal("2"),
                unita_misura="SET",
                e_rettifica=False,
            ),
        ),
    )


def assegnazione_fisica() -> AssegnazioneFisica:
    return AssegnazioneFisica(
        assegnazione_id=AssegnazioneFisicaId("ASF-000001"),
        raccolta_id=RaccoltaId("RAC-000001"),
        ordine_id=OrdineId("ORD-000001"),
        riga_ordine_posizione=1,
        consegna_id=ConsegnaId("CON-000001"),
        quantita_assegnata=Decimal("2"),
        unita_misura="SET",
        effective_at=datetime(2026, 9, 20, 8, 0, tzinfo=UTC),
        motivo="Assegnazione automatica",
    )


def fattura() -> Fattura:
    return Fattura(
        numero_fattura=NumeroFattura("2026/0001"),
        cliente_id=ClienteId("CLI-000001"),
        cliente_denominazione="Abaluus",
        data_emissione=date(2026, 9, 1),
        scadenza=date(2026, 10, 1),
        totale_netto=Decimal("100.00"),
        totale_igic=Decimal("7.00"),
        totale=Decimal("107.00"),
        rettifica_di=None,
        consegne_collegate=(ConsegnaId("CON-000001"),),
        righe=(
            RigaFattura(
                posizione=1,
                varieta_id=VarietaId("VAR-000002"),
                varieta_denominazione="Rábano",
                quantita=Decimal("2"),
                unita_misura="SET",
                prezzo_unitario=Decimal("50.00"),
                aliquota_igic=Decimal("7"),
                importo_netto=Decimal("100.00"),
                importo_igic=Decimal("7.00"),
            ),
        ),
    )


def incasso() -> Incasso:
    return Incasso(
        incasso_id=IncassoId("INC-000001"),
        fattura_numero=NumeroFattura("2026/0001"),
        importo=Decimal("107.00"),
        data_incasso=date(2026, 9, 10),
        metodo="BONIFICO",
        note=None,
        rettifica_incasso_id=None,
        created_at=datetime(2026, 9, 10, 9, 0, tzinfo=UTC),
    )


def uscita() -> Uscita:
    return Uscita(
        uscita_id=UscitaId("USC-000001"),
        importo=Decimal("25.00"),
        data_uscita=date(2026, 9, 1),
        categoria="SEMENTI",
        beneficiario="Hyfarm",
        metodo="BONIFICO",
        note=None,
        rettifica_uscita_id=None,
        created_at=datetime(2026, 9, 1, 9, 0, tzinfo=UTC),
    )


def run() -> Run:
    return Run(
        run_id=RunId("RUN-000001"),
        started_at=datetime(2026, 9, 10, 6, 0, tzinfo=UTC),
        completed_at=datetime(2026, 9, 10, 6, 1, tzinfo=UTC),
        simulation=False,
        state="SUCCESS",
        programmi_letti=9,
        righe_valutate=12,
        occorrenze_valutate=3,
        ordini_generati=1,
        elementi_saltati=0,
        messaggi=(),
    )


def run_log() -> RunLog:
    return RunLog(
        run_id=RunId("RUN-000001"),
        voci=(
            RunLogVoce(
                occurred_at=datetime(2026, 9, 10, 6, 0, 1, tzinfo=UTC),
                level="INFO",
                event_type="RUN_STARTED",
                message="Avvio RUN pianificata.",
                context={},
            ),
        ),
    )
