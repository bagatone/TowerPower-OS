"""DISPONIBILITA_COMMERCIALE -- pagina e API standalone (per varietà)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ...application.disponibilita_commerciale.models import RichiediDisponibilitaCommerciale
from ...application.disponibilita_commerciale.service import DisponibilitaCommercialeService
from ...domain.identifiers import VarietaId
from ..deps import get_disponibilita_commerciale_service
from ..rendering import render_detail_page
from ..serialize import to_jsonable

router = APIRouter()


@router.get("/api/disponibilita-commerciale/{varieta_id}")
def api_disponibilita(
    varieta_id: str,
    service: DisponibilitaCommercialeService = Depends(get_disponibilita_commerciale_service),
) -> dict:
    disponibilita = service.disponibilita(RichiediDisponibilitaCommerciale(VarietaId(varieta_id)))
    return to_jsonable(disponibilita)


@router.get("/disponibilita-commerciale/{varieta_id}", response_class=HTMLResponse)
def pagina_disponibilita(
    varieta_id: str,
    service: DisponibilitaCommercialeService = Depends(get_disponibilita_commerciale_service),
) -> str:
    disponibilita = service.disponibilita(RichiediDisponibilitaCommerciale(VarietaId(varieta_id)))
    item = to_jsonable(disponibilita)
    return render_detail_page(
        title=f"Disponibilità commerciale {item['varieta_id']}",
        subtitle="DISPONIBILE - PRENOTATO = VENDIBILE",
        item=item,
    )
