from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.fornitura_ordini_consegne_lettura.errors import (
    InvalidFornituraOrdiniConsegneLetturaQueryError,
)
from src.tpo_core.application.fornitura_ordini_consegne_lettura.models import (
    AssegnazioneFisica, Consegna, ElencoAssegnazioniFisiche, ElencoConsegne, ElencoOrdini,
    ElencoProgrammiFornitura, Ordine, ProgrammaFornitura, RichiediElencoAssegnazioniFisiche,
    RichiediElencoConsegne, RichiediElencoOrdini, RichiediElencoProgrammiFornitura,
    RigaConsegna, RigaOrdine, RigaProgrammaFornitura,
)
from src.tpo_core.application.fornitura_ordini_consegne_lettura.service import (
    FornituraOrdiniConsegneLetturaService,
)
from src.tpo_core.domain.identifiers import (
    AssegnazioneFisicaId, ClienteId, ConsegnaId, OrdineId, ProgrammaFornituraId, RaccoltaId,
    VarietaId,
)

NOW = datetime(2099, 1, 1, tzinfo=timezone.utc)
OGGI = date(2099, 1, 1)


def _riga_programma(**overrides):
    base = dict(
        posizione=1, varieta_id=VarietaId("VAR-000001"), varieta_denominazione="Rucola",
        quantita=Decimal("50"), unita_misura="GRAM", tipo_ricorrenza="SETTIMANALE",
        intervallo_giorni=None, giorni_settimana=(),
    )
    base.update(overrides)
    return RigaProgrammaFornitura(**base)


def _programma(**overrides):
    base = dict(
        programma_id=ProgrammaFornituraId("PF-000001"), cliente_id=ClienteId("CLI-000001"),
        cliente_denominazione="Ristorante Sole", numero_versione=1, stato="ATTIVO",
        data_inizio=OGGI, data_fine=None, finestra_operativa_giorni=2, valida_dal=NOW,
        righe=(),
    )
    base.update(overrides)
    return ProgrammaFornitura(**base)


def _ordine(**overrides):
    base = dict(
        ordine_id=OrdineId("ORD-000001"), cliente_id=ClienteId("CLI-000001"),
        cliente_denominazione="Ristorante Sole", programma_fornitura_id=None,
        data_ordine=OGGI, data_consegna_prevista=None, stato="APERTO",
        tipo_creazione="MANUALE", righe=(),
    )
    base.update(overrides)
    return Ordine(**base)


def _consegna(**overrides):
    base = dict(
        consegna_id=ConsegnaId("CON-000001"), cliente_id=ClienteId("CLI-000001"),
        cliente_denominazione="Ristorante Sole", stato="PROGRAMMATA", data_prevista=OGGI,
        data_effettiva=None, destinazione_fisica=None, ordini_collegati=(), righe=(),
    )
    base.update(overrides)
    return Consegna(**base)


def _assegnazione(**overrides):
    base = dict(
        assegnazione_id=AssegnazioneFisicaId("ASF-000001"), raccolta_id=RaccoltaId("RAC-000001"),
        ordine_id=OrdineId("ORD-000001"), riga_ordine_posizione=1, consegna_id=None,
        quantita_assegnata=Decimal("2"), unita_misura="SET", effective_at=NOW,
        motivo="raccolto fresco",
    )
    base.update(overrides)
    return AssegnazioneFisica(**base)


def test_riga_programma_requires_intervallo_iff_ogni_x_giorni():
    with pytest.raises(InvalidFornituraOrdiniConsegneLetturaQueryError):
        _riga_programma(tipo_ricorrenza="OGNI_X_GIORNI", intervallo_giorni=None)
    with pytest.raises(InvalidFornituraOrdiniConsegneLetturaQueryError):
        _riga_programma(tipo_ricorrenza="SETTIMANALE", intervallo_giorni=5)


def test_riga_programma_rejects_giorno_out_of_range():
    with pytest.raises(InvalidFornituraOrdiniConsegneLetturaQueryError):
        _riga_programma(tipo_ricorrenza="GIORNI_SETTIMANA", giorni_settimana=(0,))
    with pytest.raises(InvalidFornituraOrdiniConsegneLetturaQueryError):
        _riga_programma(tipo_ricorrenza="GIORNI_SETTIMANA", giorni_settimana=(8,))


def test_programma_rejects_data_fine_before_data_inizio():
    with pytest.raises(InvalidFornituraOrdiniConsegneLetturaQueryError):
        _programma(data_fine=date(2098, 1, 1))


def test_programma_rejects_invalid_stato():
    with pytest.raises(InvalidFornituraOrdiniConsegneLetturaQueryError):
        _programma(stato="ALTRO")


def test_programma_data_ripresa_prevista_facoltativa():
    assert _programma().data_ripresa_prevista is None
    assert _programma(
        data_ripresa_prevista=date(2099, 2, 1)
    ).data_ripresa_prevista == date(2099, 2, 1)


def test_programma_rejects_invalid_data_ripresa_prevista():
    with pytest.raises(InvalidFornituraOrdiniConsegneLetturaQueryError):
        _programma(data_ripresa_prevista="2099-02-01")
    with pytest.raises(InvalidFornituraOrdiniConsegneLetturaQueryError):
        _programma(data_ripresa_prevista=datetime(2099, 2, 1, tzinfo=timezone.utc))


def test_ordine_rejects_consegna_prevista_before_ordine():
    with pytest.raises(InvalidFornituraOrdiniConsegneLetturaQueryError):
        _ordine(data_consegna_prevista=date(2098, 1, 1))


def test_riga_consegna_rejects_zero_quantita():
    with pytest.raises(InvalidFornituraOrdiniConsegneLetturaQueryError):
        RigaConsegna(1, VarietaId("VAR-000001"), "Rucola", Decimal("0"), "SET", False)


def test_riga_consegna_allows_negative_quantita_for_rettifica():
    riga = RigaConsegna(1, VarietaId("VAR-000001"), "Rucola", Decimal("-0.25"), "SET", True)
    assert riga.e_rettifica is True


def test_consegna_rejects_invalid_stato():
    with pytest.raises(InvalidFornituraOrdiniConsegneLetturaQueryError):
        _consegna(stato="SPEDITA")


def test_assegnazione_rejects_non_positive_quantita():
    with pytest.raises(InvalidFornituraOrdiniConsegneLetturaQueryError):
        _assegnazione(quantita_assegnata=Decimal("0"))


def test_assegnazione_rejects_blank_motivo():
    with pytest.raises(InvalidFornituraOrdiniConsegneLetturaQueryError):
        _assegnazione(motivo="   ")


class _FakeReader:
    def __init__(self):
        self.queries = {}

    def programmi_fornitura(self, query):
        self.queries["programmi_fornitura"] = query
        return ElencoProgrammiFornitura(())

    def ordini(self, query):
        self.queries["ordini"] = query
        return ElencoOrdini(())

    def consegne(self, query):
        self.queries["consegne"] = query
        return ElencoConsegne(())

    def assegnazioni_fisiche(self, query):
        self.queries["assegnazioni_fisiche"] = query
        return ElencoAssegnazioniFisiche(())


def test_service_delegates_all_four_queries():
    reader = _FakeReader()
    service = FornituraOrdiniConsegneLetturaService(reader)
    assert service.programmi_fornitura(RichiediElencoProgrammiFornitura()) == (
        ElencoProgrammiFornitura(())
    )
    assert service.ordini(RichiediElencoOrdini()) == ElencoOrdini(())
    assert service.consegne(RichiediElencoConsegne()) == ElencoConsegne(())
    assert service.assegnazioni_fisiche(RichiediElencoAssegnazioniFisiche()) == (
        ElencoAssegnazioniFisiche(())
    )
    assert set(reader.queries) == {
        "programmi_fornitura", "ordini", "consegne", "assegnazioni_fisiche",
    }


def test_service_rejects_invalid_query_types():
    service = FornituraOrdiniConsegneLetturaService(_FakeReader())
    with pytest.raises(InvalidFornituraOrdiniConsegneLetturaQueryError):
        service.programmi_fornitura(object())
    with pytest.raises(InvalidFornituraOrdiniConsegneLetturaQueryError):
        service.ordini(object())
    with pytest.raises(InvalidFornituraOrdiniConsegneLetturaQueryError):
        service.consegne(object())
    with pytest.raises(InvalidFornituraOrdiniConsegneLetturaQueryError):
        service.assegnazioni_fisiche(object())
