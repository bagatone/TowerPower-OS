"""CLIENTI -- pagine e API di sola lettura (boundary clienti_lettura)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ...application.clienti_lettura.models import RichiediCliente, RichiediElencoClienti
from ...application.clienti_lettura.service import ClientiLetturaService
from ...domain.identifiers import ClienteId
from ..deps import get_clienti_service
from ..rendering import render_detail_page, render_list_page
from ..serialize import to_jsonable

router = APIRouter()


@router.get("/api/clienti")
def api_elenco_clienti(service: ClientiLetturaService = Depends(get_clienti_service)) -> dict:
    elenco = service.elenco(RichiediElencoClienti())
    return {"clienti": [to_jsonable(c) for c in elenco.clienti]}


@router.get("/clienti", response_class=HTMLResponse)
def pagina_elenco_clienti(service: ClientiLetturaService = Depends(get_clienti_service)) -> str:
    elenco = service.elenco(RichiediElencoClienti())
    items = [to_jsonable(c) for c in elenco.clienti]
    return render_list_page(
        title="Clienti",
        subtitle="Anagrafica CLIENTE (tpo.clienti), sola lettura.",
        items=items,
        id_field="cliente_id",
        detail_path=lambda item: f"/clienti/{item['cliente_id']}",
    )


@router.get("/api/clienti/{cliente_id}")
def api_cliente(
    cliente_id: str, service: ClientiLetturaService = Depends(get_clienti_service)
) -> dict:
    cliente = service.cliente(RichiediCliente(ClienteId(cliente_id)))
    return to_jsonable(cliente)


@router.get("/clienti/{cliente_id}", response_class=HTMLResponse)
def pagina_cliente(
    cliente_id: str, service: ClientiLetturaService = Depends(get_clienti_service)
) -> str:
    cliente = service.cliente(RichiediCliente(ClienteId(cliente_id)))
    item = to_jsonable(cliente)
    return render_detail_page(
        title=f"Cliente {item['cliente_id']}",
        subtitle=item.get("denominazione", ""),
        item=item,
    )
