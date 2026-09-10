"""Traduzione delle eccezioni applicative esistenti in risposte HTTP.

Autorità: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md,
Owner Decision D3 -- il web adapter traduce i codici di errore già
definiti da ciascun boundary applicativo (l'attributo `.code` presente su
ogni eccezione dei moduli application/*_lettura/errors.py) in una
risposta HTTP; non introduce nuove categorie di errore o regole di
validazione. La convenzione dei `.code` esistenti (suffisso
`_NOT_FOUND` / `_INPUT_INVALID`) è quella che decide lo status HTTP.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from ..domain.errors import DomainError
from ..infrastructure.postgresql.errors import PostgreSQLError
from .rendering import render_error_page

# Le classi base di ogni boundary di lettura Fase 1: ognuna definisce le
# proprie sottoclassi con un attributo di classe `.code` (vedi
# application/<boundary>/errors.py). Registrate esplicitamente (non un
# generico `except Exception`) così un bug applicativo non previsto resta
# visibile invece di essere tradotto in una risposta 500 silenziosa.
from ..application.clienti_lettura.errors import ClientiLetturaError
from ..application.disponibilita_commerciale.errors import DisponibilitaCommercialeError
from ..application.finanze_lettura.errors import FinanzeLetturaError
from ..application.fornitura_ordini_consegne_lettura.errors import (
    FornituraOrdiniConsegneLetturaError,
)
from ..application.magazzino_lettura.errors import MagazzinoLetturaError
from ..application.run_lettura.errors import RunLetturaError
from ..application.semente_lettura.errors import SementeLetturaError
from ..application.semina_raccolta_lettura.errors import SeminaRaccoltaLetturaError
from ..application.varieta_lettura.errors import VarietaLetturaError

_BOUNDARY_ERROR_TYPES = (
    ClientiLetturaError,
    VarietaLetturaError,
    SementeLetturaError,
    SeminaRaccoltaLetturaError,
    MagazzinoLetturaError,
    FornituraOrdiniConsegneLetturaError,
    FinanzeLetturaError,
    RunLetturaError,
    DisponibilitaCommercialeError,
)


def _status_for_code(code: str) -> int:
    if code.endswith("_NOT_FOUND"):
        return 404
    if code.endswith("_INPUT_INVALID"):
        return 400
    return 500


def _respond(request: Request, *, status: int, code: str, message: str) -> Response:
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=status, content={"code": code, "message": message})
    return HTMLResponse(status_code=status, content=render_error_page(status, code, message))


async def _handle_boundary_error(request: Request, exc: Exception) -> Response:
    code = getattr(exc, "code", type(exc).__name__)
    message = str(exc) or code
    return _respond(request, status=_status_for_code(code), code=code, message=message)


async def _handle_domain_error(request: Request, exc: Exception) -> Response:
    # Es. InvalidIdentifierError: un identificativo nell'URL non rispetta
    # il formato (PREFISSO-NNNNNN / NumeroFattura AAAA/NNNN). Non è
    # un'eccezione di boundary (non ha `.code`) ma è comunque un errore di
    # input dell'utente, non un bug -- 400, non 500.
    return _respond(
        request, status=400, code=type(exc).__name__, message=str(exc) or type(exc).__name__
    )


async def _handle_database_error(request: Request, exc: Exception) -> Response:
    return _respond(
        request,
        status=503,
        code="DATABASE_UNAVAILABLE",
        message="Il database non è raggiungibile in questo momento.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    for error_type in _BOUNDARY_ERROR_TYPES:
        app.add_exception_handler(error_type, _handle_boundary_error)
    app.add_exception_handler(DomainError, _handle_domain_error)
    app.add_exception_handler(PostgreSQLError, _handle_database_error)
