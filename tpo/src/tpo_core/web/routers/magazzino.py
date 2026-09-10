"""MAGAZZINO -- STOCK / MOVIMENTO / ARTICOLO, pagine e API di sola lettura
(boundary magazzino_lettura). Tutte e tre le query sono elenchi completi
(nessun dettaglio singolo esposto dall'Application layer oggi)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ...application.magazzino_lettura.models import (
    RichiediElencoArticoli, RichiediElencoMovimenti, RichiediElencoStock,
)
from ...application.magazzino_lettura.service import MagazzinoLetturaService
from ..deps import get_magazzino_service
from ..rendering import render_list_page, render_page, render_table
from ..serialize import to_jsonable

router = APIRouter()


@router.get("/api/magazzino/articoli")
def api_articoli(service: MagazzinoLetturaService = Depends(get_magazzino_service)) -> dict:
    elenco = service.articoli(RichiediElencoArticoli())
    return {"articoli": [to_jsonable(a) for a in elenco.articoli]}


@router.get("/magazzino/articoli", response_class=HTMLResponse)
def pagina_articoli(service: MagazzinoLetturaService = Depends(get_magazzino_service)) -> str:
    elenco = service.articoli(RichiediElencoArticoli())
    items = [to_jsonable(a) for a in elenco.articoli]
    return render_list_page(
        title="Articoli",
        subtitle="Anagrafica ARTICOLO -- materiali della catena (tpo.articoli), sola lettura.",
        items=items,
    )


@router.get("/api/magazzino/stock")
def api_stock(service: MagazzinoLetturaService = Depends(get_magazzino_service)) -> dict:
    elenco = service.stock(RichiediElencoStock())
    return to_jsonable(elenco)


@router.get("/magazzino/stock", response_class=HTMLResponse)
def pagina_stock(service: MagazzinoLetturaService = Depends(get_magazzino_service)) -> str:
    elenco = service.stock(RichiediElencoStock())
    jsonable = to_jsonable(elenco)
    body = (
        "<h1>Magazzino — Stock</h1>"
        '<p class="subtitle">tpo.stock (VARIETA) e tpo.stock_articoli (ARTICOLO), sola lettura.</p>'
        f"<h2>Stock varietà ({len(jsonable['stock_varieta'])})</h2>"
        f"{render_table(jsonable['stock_varieta'])}"
        f"<h2>Stock articoli ({len(jsonable['stock_articoli'])})</h2>"
        f"{render_table(jsonable['stock_articoli'])}"
    )
    return render_page("Magazzino — Stock", body)


@router.get("/api/magazzino/movimenti")
def api_movimenti(service: MagazzinoLetturaService = Depends(get_magazzino_service)) -> dict:
    elenco = service.movimenti(RichiediElencoMovimenti())
    return {"movimenti": [to_jsonable(m) for m in elenco.movimenti]}


@router.get("/magazzino/movimenti", response_class=HTMLResponse)
def pagina_movimenti(service: MagazzinoLetturaService = Depends(get_magazzino_service)) -> str:
    elenco = service.movimenti(RichiediElencoMovimenti())
    items = [to_jsonable(m) for m in elenco.movimenti]
    return render_list_page(
        title="Magazzino — Movimenti",
        subtitle="Registro MOVIMENTO_MAGAZZINO (tpo.movimenti_magazzino), sola lettura.",
        items=items,
    )
