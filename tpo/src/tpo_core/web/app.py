"""Composition root del web adapter Fase 1 (OPERATIONAL_WEB_ADAPTER).

Autorità: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md.
Espone i 9 boundary applicativi di sola lettura già esistenti come API
JSON (`/api/...`) e pagine HTML semplici (`/...`), senza introdurre alcuna
scrittura, alcun secondo Writer o alcuna regola di validazione nuova (D3,
Sezione 5). Non legge mai Google Sheets direttamente. Pensato per l'uso
in LAN (D4): nessuna autenticazione in Fase 1 -- non esporre questa
applicazione su Internet.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .errors import register_exception_handlers
from .rendering import render_index_page
from .routers import (
    clienti, disponibilita_commerciale, finanze, fornitura, magazzino, run,
    semente, semina_raccolta, varieta,
)

_ROUTERS = (
    clienti.router,
    varieta.router,
    disponibilita_commerciale.router,
    semente.router,
    semina_raccolta.router,
    magazzino.router,
    fornitura.router,
    finanze.router,
    run.router,
)


def create_app(postgresql_settings: PostgreSQLSettings) -> FastAPI:
    if not isinstance(postgresql_settings, PostgreSQLSettings):
        raise TypeError("postgresql_settings deve essere PostgreSQLSettings.")

    app = FastAPI(
        title="Tower Power OS — Sala Operativa",
        description=(
            "OPERATIONAL_WEB_ADAPTER Fase 1: query a sola lettura sui 9 boundary "
            "applicativi già esistenti. Nessuna scrittura è possibile da questa API."
        ),
    )
    app.state.postgresql_settings = postgresql_settings

    for router in _ROUTERS:
        app.include_router(router)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home() -> str:
        return render_index_page()

    register_exception_handlers(app)
    return app
