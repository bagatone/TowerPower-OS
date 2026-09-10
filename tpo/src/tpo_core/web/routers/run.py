"""RUN / RUN_LOG -- pagine e API di sola lettura (boundary run_lettura).

L'elenco RUN è il riepilogo di ogni esecuzione dello scheduler delle 06:00
(messaggi di warning/errore già annidati); il "dettaglio" per singolo run
è invece il suo RUN_LOG (voci di log passo-passo), una query separata
(RichiediRunLog) -- non un duplicato del riepilogo."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ...application.run_lettura.models import RichiediElencoRun, RichiediRunLog
from ...application.run_lettura.service import RunLetturaService
from ...domain.identifiers import RunId
from ..deps import get_run_service
from ..rendering import render_detail_page, render_list_page
from ..serialize import to_jsonable

router = APIRouter()


@router.get("/api/run")
def api_elenco_run(service: RunLetturaService = Depends(get_run_service)) -> dict:
    elenco = service.elenco(RichiediElencoRun())
    return {"runs": [to_jsonable(r) for r in elenco.runs]}


@router.get("/run", response_class=HTMLResponse)
def pagina_elenco_run(service: RunLetturaService = Depends(get_run_service)) -> str:
    elenco = service.elenco(RichiediElencoRun())
    items = [to_jsonable(r) for r in elenco.runs]
    return render_list_page(
        title="Run scheduler",
        subtitle="Riepilogo RUN dello Scheduling Engine (esecuzione delle 06:00), sola lettura.",
        items=items,
        id_field="run_id",
        detail_path=lambda item: f"/run/{item['run_id']}/log",
    )


@router.get("/api/run/{run_id}/log")
def api_run_log(run_id: str, service: RunLetturaService = Depends(get_run_service)) -> dict:
    log = service.log(RichiediRunLog(RunId(run_id)))
    return to_jsonable(log)


@router.get("/run/{run_id}/log", response_class=HTMLResponse)
def pagina_run_log(run_id: str, service: RunLetturaService = Depends(get_run_service)) -> str:
    log = service.log(RichiediRunLog(RunId(run_id)))
    item = to_jsonable(log)
    return render_detail_page(
        title=f"Log RUN {item['run_id']}",
        subtitle=f"{len(item.get('voci', []))} voci di log",
        item=item,
    )
