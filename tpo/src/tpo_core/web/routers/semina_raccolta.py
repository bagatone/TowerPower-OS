"""SEMINA / RACCOLTA -- pagine e API di sola lettura (boundary
semina_raccolta_lettura). RACCOLTA non ha una vista propria: appare solo
annidata dentro la SEMINA a cui appartiene (esattamente come nel modello
applicativo Semina.raccolte)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ...application.semina_raccolta_lettura.models import RichiediElencoSemine, RichiediSemina
from ...application.semina_raccolta_lettura.service import SeminaRaccoltaLetturaService
from ...domain.identifiers import SeminaId
from ..deps import get_semina_raccolta_service
from ..rendering import render_detail_page, render_list_page
from ..serialize import to_jsonable

router = APIRouter()


@router.get("/api/semine")
def api_elenco_semine(
    service: SeminaRaccoltaLetturaService = Depends(get_semina_raccolta_service),
) -> dict:
    elenco = service.elenco(RichiediElencoSemine())
    return {"semine": [to_jsonable(s) for s in elenco.semine]}


@router.get("/semine", response_class=HTMLResponse)
def pagina_elenco_semine(
    service: SeminaRaccoltaLetturaService = Depends(get_semina_raccolta_service),
) -> str:
    elenco = service.elenco(RichiediElencoSemine())
    items = [to_jsonable(s) for s in elenco.semine]
    for item in items:
        item.pop("raccolte", None)  # in elenco solo il riepilogo, non i dettagli raccolta
    return render_list_page(
        title="Semine",
        subtitle="Ciclo SEMINA (tpo.semine), sola lettura.",
        items=items,
        id_field="semina_id",
        detail_path=lambda item: f"/semine/{item['semina_id']}",
    )


@router.get("/api/semine/{semina_id}")
def api_semina(
    semina_id: str,
    service: SeminaRaccoltaLetturaService = Depends(get_semina_raccolta_service),
) -> dict:
    semina = service.semina(RichiediSemina(SeminaId(semina_id)))
    return to_jsonable(semina)


@router.get("/semine/{semina_id}", response_class=HTMLResponse)
def pagina_semina(
    semina_id: str,
    service: SeminaRaccoltaLetturaService = Depends(get_semina_raccolta_service),
) -> str:
    semina = service.semina(RichiediSemina(SeminaId(semina_id)))
    item = to_jsonable(semina)
    return render_detail_page(
        title=f"Semina {item['semina_id']}",
        subtitle=f"{item.get('varieta_denominazione', '')} — stato {item.get('stato', '')}",
        item=item,
    )
