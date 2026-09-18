"""DA SEMINARE -- pagina e API di sola lettura (boundary
pianificazione_semina_lettura, decimo boundary OPERATIONAL_WEB_ADAPTER).

Mostra le righe piano semina non ancora avviate della revisione corrente,
ordinate per data/ora di semina piu' vicina -- vedi Fatto 18 della roadmap
del progetto Claude "TPO system" per la richiesta esplicita dell'owner."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ...application.pianificazione_semina_lettura.models import RichiediElencoDaSeminare
from ...application.pianificazione_semina_lettura.service import (
    PianificazioneSeminaLetturaService,
)
from ..deps import get_pianificazione_semina_service
from ..rendering import render_list_page
from ..serialize import to_jsonable

router = APIRouter()


@router.get("/api/da-seminare")
def api_da_seminare(
    service: PianificazioneSeminaLetturaService = Depends(get_pianificazione_semina_service),
) -> dict:
    elenco = service.elenco(RichiediElencoDaSeminare())
    return {"righe": [to_jsonable(r) for r in elenco.righe]}


@router.get("/da-seminare", response_class=HTMLResponse)
def pagina_da_seminare(
    service: PianificazioneSeminaLetturaService = Depends(get_pianificazione_semina_service),
) -> str:
    elenco = service.elenco(RichiediElencoDaSeminare())
    items = [to_jsonable(r) for r in elenco.righe]
    return render_list_page(
        title="Da seminare",
        subtitle=(
            "Righe del piano di produzione non ancora avviate (PIANIFICATA/PRONTA/"
            "TARDIVA), ordinate per data di semina piu' vicina. Calcolate "
            "automaticamente ogni giorno alle 6:30 da Production Planning, a "
            "ritroso dalla data di consegna di ciascun ordine."
        ),
        items=items,
    )
