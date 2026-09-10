"""SEMENTE / LOTTO_SEME -- pagine e API di sola lettura (boundary
semente_lettura). Il catalogo SEMENTI (fornitori/referenze) non ha una
query di dettaglio singolo nell'Application layer (solo elenco_sementi):
la pagina /sementi è quindi solo un elenco, senza link di dettaglio --
non un'omissione, riflette esattamente ciò che il boundary espone oggi.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ...application.semente_lettura.models import (
    RichiediElencoLotti, RichiediElencoSementi, RichiediLotto,
)
from ...application.semente_lettura.service import SementeLetturaService
from ...domain.identifiers import LottoSemeId
from ..deps import get_semente_service
from ..rendering import render_detail_page, render_list_page
from ..serialize import to_jsonable

router = APIRouter()


@router.get("/api/sementi")
def api_elenco_sementi(service: SementeLetturaService = Depends(get_semente_service)) -> dict:
    elenco = service.elenco_sementi(RichiediElencoSementi())
    return {"sementi": [to_jsonable(s) for s in elenco.sementi]}


@router.get("/sementi", response_class=HTMLResponse)
def pagina_elenco_sementi(service: SementeLetturaService = Depends(get_semente_service)) -> str:
    elenco = service.elenco_sementi(RichiediElencoSementi())
    items = [to_jsonable(s) for s in elenco.sementi]
    return render_list_page(
        title="Sementi",
        subtitle="Catalogo fornitori/referenze SEMENTE (tpo.sementi), sola lettura.",
        items=items,
    )


@router.get("/api/lotti-seme")
def api_elenco_lotti(service: SementeLetturaService = Depends(get_semente_service)) -> dict:
    elenco = service.elenco_lotti(RichiediElencoLotti())
    return {"lotti": [to_jsonable(l) for l in elenco.lotti]}


@router.get("/lotti-seme", response_class=HTMLResponse)
def pagina_elenco_lotti(service: SementeLetturaService = Depends(get_semente_service)) -> str:
    elenco = service.elenco_lotti(RichiediElencoLotti())
    items = [to_jsonable(l) for l in elenco.lotti]
    return render_list_page(
        title="Lotti seme",
        subtitle="Registro LOTTO_SEME (tpo.lotti_seme), sola lettura.",
        items=items,
        id_field="lotto_seme_id",
        detail_path=lambda item: f"/lotti-seme/{item['lotto_seme_id']}",
    )


@router.get("/api/lotti-seme/{lotto_seme_id}")
def api_lotto(
    lotto_seme_id: str, service: SementeLetturaService = Depends(get_semente_service)
) -> dict:
    lotto = service.lotto(RichiediLotto(LottoSemeId(lotto_seme_id)))
    return to_jsonable(lotto)


@router.get("/lotti-seme/{lotto_seme_id}", response_class=HTMLResponse)
def pagina_lotto(
    lotto_seme_id: str, service: SementeLetturaService = Depends(get_semente_service)
) -> str:
    lotto = service.lotto(RichiediLotto(LottoSemeId(lotto_seme_id)))
    item = to_jsonable(lotto)
    return render_detail_page(
        title=f"Lotto seme {item['lotto_seme_id']}",
        subtitle=f"{item.get('semente_fornitore', '')} — {item.get('semente_referenza_commerciale', '')}",
        item=item,
    )
