"""Dependency injection dei 10 servizi applicativi di lettura Fase 1.

Ogni funzione costruisce il proprio servizio chiamando l'esistente
composition root in `bootstrap/<boundary>.py` (mai una connessione o una
query scritta qui): il web adapter non è un secondo Writer né un secondo
punto di composizione, si limita a usare l'Application layer già
esistente (docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md
Sezione 5). L'import di ciascun modulo `bootstrap.*` (e quindi del reader
PostgreSQL reale che comporta) avviene dentro la funzione, non in testa al
modulo: una connessione (lazy: `PostgreSQLConnectionFactory.connect()` non
viene mai chiamata qui, solo all'esecuzione di una query) si apre solo
quando una richiesta HTTP la usa davvero.
"""
from __future__ import annotations

from fastapi import Request

from ..application.clienti_lettura.service import ClientiLetturaService
from ..application.disponibilita_commerciale.service import DisponibilitaCommercialeService
from ..application.finanze_lettura.service import FinanzeLetturaService
from ..application.fornitura_ordini_consegne_lettura.service import (
    FornituraOrdiniConsegneLetturaService,
)
from ..application.magazzino_lettura.service import MagazzinoLetturaService
from ..application.run_lettura.service import RunLetturaService
from ..application.pianificazione_semina_lettura.service import (
    PianificazioneSeminaLetturaService,
)
from ..application.semente_lettura.service import SementeLetturaService
from ..application.semina_raccolta_lettura.service import SeminaRaccoltaLetturaService
from ..application.varieta_lettura.service import VarietaLetturaService
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def _settings(request: Request) -> PostgreSQLSettings:
    return request.app.state.postgresql_settings


def get_clienti_service(request: Request) -> ClientiLetturaService:
    from ..bootstrap.clienti_lettura import build_clienti_lettura_service

    return build_clienti_lettura_service(_settings(request))


def get_varieta_service(request: Request) -> VarietaLetturaService:
    from ..bootstrap.varieta_lettura import build_varieta_lettura_service

    return build_varieta_lettura_service(_settings(request))


def get_disponibilita_commerciale_service(request: Request) -> DisponibilitaCommercialeService:
    from ..bootstrap.disponibilita_commerciale import build_disponibilita_commerciale_service

    return build_disponibilita_commerciale_service(_settings(request))


def get_semente_service(request: Request) -> SementeLetturaService:
    from ..bootstrap.semente_lettura import build_semente_lettura_service

    return build_semente_lettura_service(_settings(request))


def get_semina_raccolta_service(request: Request) -> SeminaRaccoltaLetturaService:
    from ..bootstrap.semina_raccolta_lettura import build_semina_raccolta_lettura_service

    return build_semina_raccolta_lettura_service(_settings(request))


def get_magazzino_service(request: Request) -> MagazzinoLetturaService:
    from ..bootstrap.magazzino_lettura import build_magazzino_lettura_service

    return build_magazzino_lettura_service(_settings(request))


def get_fornitura_service(request: Request) -> FornituraOrdiniConsegneLetturaService:
    from ..bootstrap.fornitura_ordini_consegne_lettura import (
        build_fornitura_ordini_consegne_lettura_service,
    )

    return build_fornitura_ordini_consegne_lettura_service(_settings(request))


def get_finanze_service(request: Request) -> FinanzeLetturaService:
    from ..bootstrap.finanze_lettura import build_finanze_lettura_service

    return build_finanze_lettura_service(_settings(request))


def get_run_service(request: Request) -> RunLetturaService:
    from ..bootstrap.run_lettura import build_run_lettura_service

    return build_run_lettura_service(_settings(request))


def get_pianificazione_semina_service(
    request: Request,
) -> PianificazioneSeminaLetturaService:
    from ..bootstrap.pianificazione_semina_lettura import (
        build_pianificazione_semina_lettura_service,
    )

    return build_pianificazione_semina_lettura_service(_settings(request))
