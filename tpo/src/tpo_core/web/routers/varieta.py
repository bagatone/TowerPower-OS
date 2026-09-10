"""VARIETA -- pagine e API di sola lettura (boundary varieta_lettura).

La pagina di dettaglio include anche, quando disponibile, la
DISPONIBILITA_COMMERCIALE della stessa varietà (boundary separato):
se la query fallisce con VarietaId non trovato in tpo.stock (varietà
senza ancora un movimento di magazzino registrato) la sezione viene
semplicemente omessa, senza far fallire la pagina -- non è
un'invenzione di dato, è un'assenza reale che viene mostrata come tale.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ...application.disponibilita_commerciale.errors import (
    DisponibilitaCommercialeVarietaNotFoundError,
)
from ...application.disponibilita_commerciale.models import RichiediDisponibilitaCommerciale
from ...application.disponibilita_commerciale.service import DisponibilitaCommercialeService
from ...application.varieta_lettura.models import RichiediElencoVarieta, RichiediVarieta
from ...application.varieta_lettura.service import VarietaLetturaService
from ...domain.identifiers import VarietaId
from ..deps import get_disponibilita_commerciale_service, get_varieta_service
from ..rendering import render_detail_page, render_list_page
from ..serialize import to_jsonable

router = APIRouter()


@router.get("/api/varieta")
def api_elenco_varieta(service: VarietaLetturaService = Depends(get_varieta_service)) -> dict:
    elenco = service.elenco(RichiediElencoVarieta())
    return {"varieta": [to_jsonable(v) for v in elenco.varieta]}


@router.get("/varieta", response_class=HTMLResponse)
def pagina_elenco_varieta(service: VarietaLetturaService = Depends(get_varieta_service)) -> str:
    elenco = service.elenco(RichiediElencoVarieta())
    items = [to_jsonable(v) for v in elenco.varieta]
    return render_list_page(
        title="Varietà",
        subtitle="Anagrafica VARIETA + LISTINO_VARIETA (tpo.varieta), sola lettura.",
        items=items,
        id_field="varieta_id",
        detail_path=lambda item: f"/varieta/{item['varieta_id']}",
    )


def _disponibilita_jsonable(
    varieta_id: VarietaId, service: DisponibilitaCommercialeService
) -> dict | None:
    try:
        disponibilita = service.disponibilita(RichiediDisponibilitaCommerciale(varieta_id))
    except DisponibilitaCommercialeVarietaNotFoundError:
        return None
    return to_jsonable(disponibilita)


@router.get("/api/varieta/{varieta_id}")
def api_varieta(
    varieta_id: str,
    service: VarietaLetturaService = Depends(get_varieta_service),
    disponibilita_service: DisponibilitaCommercialeService = Depends(
        get_disponibilita_commerciale_service
    ),
) -> dict:
    identifier = VarietaId(varieta_id)
    varieta = service.varieta(RichiediVarieta(identifier))
    item = to_jsonable(varieta)
    item["disponibilita_commerciale"] = _disponibilita_jsonable(identifier, disponibilita_service)
    return item


@router.get("/varieta/{varieta_id}", response_class=HTMLResponse)
def pagina_varieta(
    varieta_id: str,
    service: VarietaLetturaService = Depends(get_varieta_service),
    disponibilita_service: DisponibilitaCommercialeService = Depends(
        get_disponibilita_commerciale_service
    ),
) -> str:
    identifier = VarietaId(varieta_id)
    varieta = service.varieta(RichiediVarieta(identifier))
    item = to_jsonable(varieta)
    item["disponibilita_commerciale"] = _disponibilita_jsonable(identifier, disponibilita_service)
    return render_detail_page(
        title=f"Varietà {item['varieta_id']}",
        subtitle=item.get("denominazione", ""),
        item=item,
    )
