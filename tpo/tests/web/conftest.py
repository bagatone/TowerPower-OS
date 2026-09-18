"""Fixture condivise per i test del web adapter (10 boundary Fase 1).

Non tocca mai PostgreSQL: ogni servizio applicativo reale (le stesse
classi `*Service` di produzione) viene costruito con un reader finto
in-memory, iniettato nell'app FastAPI tramite `app.dependency_overrides`.
Verifica quindi il vero comportamento di Service + web adapter (routing,
serializzazione, mappatura errori), non una sua reimplementazione."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.tpo_core.application.clienti_lettura.errors import ClientiLetturaClienteNotFoundError
from src.tpo_core.application.clienti_lettura.service import ClientiLetturaService
from src.tpo_core.application.disponibilita_commerciale.errors import (
    DisponibilitaCommercialeVarietaNotFoundError,
)
from src.tpo_core.application.disponibilita_commerciale.service import DisponibilitaCommercialeService
from src.tpo_core.application.finanze_lettura.service import FinanzeLetturaService
from src.tpo_core.application.fornitura_ordini_consegne_lettura.service import (
    FornituraOrdiniConsegneLetturaService,
)
from src.tpo_core.application.magazzino_lettura.models import ElencoStock
from src.tpo_core.application.magazzino_lettura.service import MagazzinoLetturaService
from src.tpo_core.application.pianificazione_semina_lettura.service import (
    PianificazioneSeminaLetturaService,
)
from src.tpo_core.application.run_lettura.errors import RunLetturaRunNotFoundError
from src.tpo_core.application.run_lettura.service import RunLetturaService
from src.tpo_core.application.semente_lettura.errors import SementeLetturaLottoNotFoundError
from src.tpo_core.application.semente_lettura.service import SementeLetturaService
from src.tpo_core.application.semina_raccolta_lettura.errors import (
    SeminaRaccoltaLetturaSeminaNotFoundError,
)
from src.tpo_core.application.semina_raccolta_lettura.service import SeminaRaccoltaLetturaService
from src.tpo_core.application.varieta_lettura.errors import VarietaLetturaVarietaNotFoundError
from src.tpo_core.application.varieta_lettura.service import VarietaLetturaService
from src.tpo_core.infrastructure.postgresql.settings import PostgreSQLSettings
from src.tpo_core.web import deps
from src.tpo_core.web.app import create_app

from . import factories as f

_DUMMY_SETTINGS = PostgreSQLSettings(
    host="localhost",
    port=5432,
    database="tpo_test",
    user="tpo",
    password="unused-in-tests",
    sslmode="require",
    connect_timeout_seconds=5,
)


class _FakeClientiReader:
    def cliente(self, query):
        if query.cliente_id.value != "CLI-000001":
            raise ClientiLetturaClienteNotFoundError("CLIENTE inesistente.")
        return f.cliente()

    def elenco(self, query):
        from src.tpo_core.application.clienti_lettura.models import ElencoClienti

        return ElencoClienti((f.cliente(),))


class _FakeVarietaReader:
    def varieta(self, query):
        if query.varieta_id.value != "VAR-000002":
            raise VarietaLetturaVarietaNotFoundError("VARIETA inesistente.")
        return f.varieta()

    def elenco(self, query):
        from src.tpo_core.application.varieta_lettura.models import ElencoVarieta

        return ElencoVarieta((f.varieta(),))


class _FakeDisponibilitaReader:
    def disponibilita(self, query):
        if query.varieta_id.value != "VAR-000002":
            raise DisponibilitaCommercialeVarietaNotFoundError("VARIETA senza stock.")
        return f.disponibilita()


class _FakeSementeReader:
    def elenco_sementi(self, query):
        from src.tpo_core.application.semente_lettura.models import ElencoSementi

        return ElencoSementi((f.semente(),))

    def lotto(self, query):
        if query.lotto_seme_id.value != "LSE-000019":
            raise SementeLetturaLottoNotFoundError("LOTTO_SEME inesistente.")
        return f.lotto_seme()

    def elenco_lotti(self, query):
        from src.tpo_core.application.semente_lettura.models import ElencoLotti

        return ElencoLotti((f.lotto_seme(),))


class _FakeSeminaRaccoltaReader:
    def semina(self, query):
        if query.semina_id.value != "SEM-000001":
            raise SeminaRaccoltaLetturaSeminaNotFoundError("SEMINA inesistente.")
        return f.semina()

    def elenco(self, query):
        from src.tpo_core.application.semina_raccolta_lettura.models import ElencoSemine

        return ElencoSemine((f.semina(),))


class _FakeMagazzinoReader:
    def articoli(self, query):
        from src.tpo_core.application.magazzino_lettura.models import ElencoArticoli

        return ElencoArticoli((f.articolo(),))

    def stock(self, query):
        return ElencoStock((f.stock_varieta(),), (f.stock_articolo(),))

    def movimenti(self, query):
        from src.tpo_core.application.magazzino_lettura.models import ElencoMovimenti

        return ElencoMovimenti((f.movimento(),))


class _FakeFornituraReader:
    def programmi_fornitura(self, query):
        from src.tpo_core.application.fornitura_ordini_consegne_lettura.models import (
            ElencoProgrammiFornitura,
        )

        return ElencoProgrammiFornitura((f.programma_fornitura(),))

    def ordini(self, query):
        from src.tpo_core.application.fornitura_ordini_consegne_lettura.models import ElencoOrdini

        return ElencoOrdini((f.ordine(),))

    def consegne(self, query):
        from src.tpo_core.application.fornitura_ordini_consegne_lettura.models import ElencoConsegne

        return ElencoConsegne((f.consegna(),))

    def assegnazioni_fisiche(self, query):
        from src.tpo_core.application.fornitura_ordini_consegne_lettura.models import (
            ElencoAssegnazioniFisiche,
        )

        return ElencoAssegnazioniFisiche((f.assegnazione_fisica(),))


class _FakeFinanzeReader:
    def fatture(self, query):
        from src.tpo_core.application.finanze_lettura.models import ElencoFatture

        return ElencoFatture((f.fattura(),))

    def incassi(self, query):
        from src.tpo_core.application.finanze_lettura.models import ElencoIncassi

        return ElencoIncassi((f.incasso(),))

    def uscite(self, query):
        from src.tpo_core.application.finanze_lettura.models import ElencoUscite

        return ElencoUscite((f.uscita(),))


class _FakePianificazioneSeminaReader:
    def elenco(self, query):
        from src.tpo_core.application.pianificazione_semina_lettura.models import (
            ElencoDaSeminare,
        )

        return ElencoDaSeminare((f.riga_da_seminare(),))


class _FakeRunReader:
    def elenco(self, query):
        from src.tpo_core.application.run_lettura.models import ElencoRun

        return ElencoRun((f.run(),))

    def log(self, query):
        if query.run_id.value != "RUN-000001":
            raise RunLetturaRunNotFoundError("RUN inesistente.")
        return f.run_log()


@pytest.fixture()
def client() -> TestClient:
    app = create_app(_DUMMY_SETTINGS)
    app.dependency_overrides[deps.get_clienti_service] = lambda: ClientiLetturaService(
        _FakeClientiReader()
    )
    app.dependency_overrides[deps.get_varieta_service] = lambda: VarietaLetturaService(
        _FakeVarietaReader()
    )
    app.dependency_overrides[deps.get_disponibilita_commerciale_service] = (
        lambda: DisponibilitaCommercialeService(_FakeDisponibilitaReader())
    )
    app.dependency_overrides[deps.get_semente_service] = lambda: SementeLetturaService(
        _FakeSementeReader()
    )
    app.dependency_overrides[deps.get_semina_raccolta_service] = (
        lambda: SeminaRaccoltaLetturaService(_FakeSeminaRaccoltaReader())
    )
    app.dependency_overrides[deps.get_magazzino_service] = lambda: MagazzinoLetturaService(
        _FakeMagazzinoReader()
    )
    app.dependency_overrides[deps.get_fornitura_service] = (
        lambda: FornituraOrdiniConsegneLetturaService(_FakeFornituraReader())
    )
    app.dependency_overrides[deps.get_finanze_service] = lambda: FinanzeLetturaService(
        _FakeFinanzeReader()
    )
    app.dependency_overrides[deps.get_run_service] = lambda: RunLetturaService(_FakeRunReader())
    app.dependency_overrides[deps.get_pianificazione_semina_service] = (
        lambda: PianificazioneSeminaLetturaService(_FakePianificazioneSeminaReader())
    )
    return TestClient(app, raise_server_exceptions=False)
