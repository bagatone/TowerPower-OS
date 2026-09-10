"""Punto d'ingresso ASGI per uvicorn.

Legge la configurazione PostgreSQL dalle variabili d'ambiente
TPO_DATABASE_* (le stesse del Secret Boundary usato da `run_tpo.sh`,
vedi scripts/web/run_web.sh) al momento dell'import: uvicorn importa
questo modulo una sola volta all'avvio del processo, non ad ogni
richiesta.
"""
from __future__ import annotations

from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .app import create_app

app = create_app(PostgreSQLSettings.from_environment())
