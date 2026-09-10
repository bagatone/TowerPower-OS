"""FINANZE -- FATTURA / INCASSO / USCITA, pagine e API di sola lettura
(boundary finanze_lettura). Tutte e tre le query sono elenchi completi
(nessun dettaglio singolo esposto dall'Application layer oggi): FATTURA
mostra già le sue righe annidate nell'elenco stesso."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ...application.finanze_lettura.models import (
    RichiediElencoFatture, RichiediElencoIncassi, RichiediElencoUscite,
)
from ...application.finanze_lettura.service import FinanzeLetturaService
from ..deps import get_finanze_service
from ..rendering import render_list_page
from ..serialize import to_jsonable

router = APIRouter()


@router.get("/api/fatture")
def api_fatture(service: FinanzeLetturaService = Depends(get_finanze_service)) -> dict:
    elenco = service.fatture(RichiediElencoFatture())
    return {"fatture": [to_jsonable(f) for f in elenco.fatture]}


@router.get("/fatture", response_class=HTMLResponse)
def pagina_fatture(service: FinanzeLetturaService = Depends(get_finanze_service)) -> str:
    elenco = service.fatture(RichiediElencoFatture())
    items = [to_jsonable(f) for f in elenco.fatture]
    return render_list_page(
        title="Fatture",
        subtitle="Registro FATTURA (tpo.fatture), sola lettura.",
        items=items,
    )


@router.get("/api/incassi")
def api_incassi(service: FinanzeLetturaService = Depends(get_finanze_service)) -> dict:
    elenco = service.incassi(RichiediElencoIncassi())
    return {"incassi": [to_jsonable(i) for i in elenco.incassi]}


@router.get("/incassi", response_class=HTMLResponse)
def pagina_incassi(service: FinanzeLetturaService = Depends(get_finanze_service)) -> str:
    elenco = service.incassi(RichiediElencoIncassi())
    items = [to_jsonable(i) for i in elenco.incassi]
    return render_list_page(
        title="Incassi",
        subtitle="Registro INCASSO (tpo.incassi), sola lettura.",
        items=items,
    )


@router.get("/api/uscite")
def api_uscite(service: FinanzeLetturaService = Depends(get_finanze_service)) -> dict:
    elenco = service.uscite(RichiediElencoUscite())
    return {"uscite": [to_jsonable(u) for u in elenco.uscite]}


@router.get("/uscite", response_class=HTMLResponse)
def pagina_uscite(service: FinanzeLetturaService = Depends(get_finanze_service)) -> str:
    elenco = service.uscite(RichiediElencoUscite())
    items = [to_jsonable(u) for u in elenco.uscite]
    return render_list_page(
        title="Uscite",
        subtitle="Registro USCITA (tpo.uscite), sola lettura.",
        items=items,
    )
