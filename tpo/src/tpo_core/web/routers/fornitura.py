"""FORNITURA / ORDINI / CONSEGNE / ASSEGNAZIONE_FISICA -- pagine e API di
sola lettura (boundary fornitura_ordini_consegne_lettura). Le quattro
query sono tutte elenchi completi (nessun dettaglio singolo esposto
dall'Application layer oggi): PROGRAMMA_FORNITURA, ORDINE e CONSEGNA
mostrano già le loro righe annidate nell'elenco stesso."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ...application.fornitura_ordini_consegne_lettura.models import (
    RichiediElencoAssegnazioniFisiche, RichiediElencoConsegne, RichiediElencoOrdini,
    RichiediElencoProgrammiFornitura,
)
from ...application.fornitura_ordini_consegne_lettura.service import (
    FornituraOrdiniConsegneLetturaService,
)
from ..deps import get_fornitura_service
from ..rendering import render_list_page
from ..serialize import to_jsonable

router = APIRouter()


@router.get("/api/programmi-fornitura")
def api_programmi_fornitura(
    service: FornituraOrdiniConsegneLetturaService = Depends(get_fornitura_service),
) -> dict:
    elenco = service.programmi_fornitura(RichiediElencoProgrammiFornitura())
    return {"programmi": [to_jsonable(p) for p in elenco.programmi]}


@router.get("/programmi-fornitura", response_class=HTMLResponse)
def pagina_programmi_fornitura(
    service: FornituraOrdiniConsegneLetturaService = Depends(get_fornitura_service),
) -> str:
    elenco = service.programmi_fornitura(RichiediElencoProgrammiFornitura())
    items = [to_jsonable(p) for p in elenco.programmi]
    return render_list_page(
        title="Programmi di fornitura",
        subtitle=(
            "PROGRAMMA_FORNITURA, solo versione corrente (tpo.programmi_fornitura_versioni), "
            "sola lettura."
        ),
        items=items,
    )


@router.get("/api/ordini")
def api_ordini(
    service: FornituraOrdiniConsegneLetturaService = Depends(get_fornitura_service),
) -> dict:
    elenco = service.ordini(RichiediElencoOrdini())
    return {"ordini": [to_jsonable(o) for o in elenco.ordini]}


@router.get("/ordini", response_class=HTMLResponse)
def pagina_ordini(
    service: FornituraOrdiniConsegneLetturaService = Depends(get_fornitura_service),
) -> str:
    elenco = service.ordini(RichiediElencoOrdini())
    items = [to_jsonable(o) for o in elenco.ordini]
    return render_list_page(
        title="Ordini",
        subtitle="Registro ORDINE (tpo.ordini), sola lettura.",
        items=items,
    )


@router.get("/api/consegne")
def api_consegne(
    service: FornituraOrdiniConsegneLetturaService = Depends(get_fornitura_service),
) -> dict:
    elenco = service.consegne(RichiediElencoConsegne())
    return {"consegne": [to_jsonable(c) for c in elenco.consegne]}


@router.get("/consegne", response_class=HTMLResponse)
def pagina_consegne(
    service: FornituraOrdiniConsegneLetturaService = Depends(get_fornitura_service),
) -> str:
    elenco = service.consegne(RichiediElencoConsegne())
    items = [to_jsonable(c) for c in elenco.consegne]
    return render_list_page(
        title="Consegne",
        subtitle="Registro CONSEGNA (tpo.consegne), sola lettura.",
        items=items,
    )


@router.get("/api/assegnazioni-fisiche")
def api_assegnazioni_fisiche(
    service: FornituraOrdiniConsegneLetturaService = Depends(get_fornitura_service),
) -> dict:
    elenco = service.assegnazioni_fisiche(RichiediElencoAssegnazioniFisiche())
    return {"assegnazioni": [to_jsonable(a) for a in elenco.assegnazioni]}


@router.get("/assegnazioni-fisiche", response_class=HTMLResponse)
def pagina_assegnazioni_fisiche(
    service: FornituraOrdiniConsegneLetturaService = Depends(get_fornitura_service),
) -> str:
    elenco = service.assegnazioni_fisiche(RichiediElencoAssegnazioniFisiche())
    items = [to_jsonable(a) for a in elenco.assegnazioni]
    return render_list_page(
        title="Assegnazioni fisiche",
        subtitle="Register ASSEGNAZIONE_FISICA (RACCOLTA <-> RIGA_ORDINE), sola lettura.",
        items=items,
    )
