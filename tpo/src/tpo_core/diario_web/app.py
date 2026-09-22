"""Servizio web del diario -- FastAPI. Due passi sempre separati: /api/interpreta
propone (non scrive mai nulla), /api/conferma esegue solo dopo che l'utente ha
visto e confermato la proposta esatta (condizione 2 dell'addendum di governance,
handoff/diario-governance-addendum.md).

Avvio locale (Matteo, per test prima del deploy):
  TPO_DATABASE_HOST=... [altre TPO_DATABASE_*] \\
  ANTHROPIC_API_KEY=... DIARIO_PASSWORD=... \\
  .venv/bin/uvicorn src.tpo_core.diario_web.app:app --reload --port 8766

Avvio su Render: vedi render.yaml e docs/architecture/DIARIO_CONVERSATIONAL_AGENT.md.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from . import actions, db_context, interpreter
from .auth import richiedi_autenticazione
from ..infrastructure.postgresql.settings import PostgreSQLSettings

app = FastAPI(title="Tower Power — Diario")

_INDEX_HTML = (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
ACTOR = os.environ.get("DIARIO_ACTOR", "giulia@towerpower")


def _settings() -> PostgreSQLSettings:
    return PostgreSQLSettings.from_environment()


@app.get("/healthz")
def healthz() -> dict:
    """Senza autenticazione, apposta: e' il probe di Render per sapere se il
    processo e' vivo, non deve toccare il database ne' richiedere una
    password (Render non ne invierebbe una). Il controllo vero, autenticato,
    che il database sia raggiungibile e' /api/salute."""
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def pagina(_: str = Depends(richiedi_autenticazione)) -> str:
    return _INDEX_HTML


@app.post("/api/interpreta")
def interpreta(body: dict, _: str = Depends(richiedi_autenticazione)) -> JSONResponse:
    testo = (body.get("testo") or "").strip()
    if not testo:
        raise HTTPException(400, "Testo vuoto.")
    settings = _settings()
    try:
        richieste = interpreter.interpreta(testo, settings)
    except Exception as exc:  # noqa: BLE001 -- mostrato all'utente, mai eseguito
        return JSONResponse({"proposte": [], "errori": [f"Interpretazione fallita: {exc}"]})

    proposte, errori = [], []
    for r in richieste:
        if r.azione == "chiarimento" or r.varieta_public_id is None:
            errori.append(r.chiarimento or "Richiesta non chiara, riformula.")
            continue
        try:
            if r.azione == "semina_commission":
                if not r.num_set:
                    errori.append(f"{r.varieta_nome}: manca il numero di SET seminati.")
                    continue
                p = actions.prepara_commission(
                    settings, r.varieta_public_id, r.varieta_nome, r.num_set,
                    r.origin, r.physical_started_at,
                )
                proposte.append({
                    "tipo": "semina_commission", "varieta_public_id": p.varieta_public_id,
                    "varieta_nome": p.varieta_nome, "lotto_seme_public_id": p.lotto_seme_public_id,
                    "protocollo_versione_public_id": p.protocollo_versione_public_id,
                    "grammi": p.grammi, "num_set": p.num_set,
                    "physical_started_at": p.physical_started_at, "origin": p.origin,
                    "residuo_dopo": p.residuo_dopo,
                })
            elif r.azione == "semina_transition":
                if not r.target_state:
                    errori.append(f"{r.varieta_nome}: non ho capito a quale stadio deve passare.")
                    continue
                p = actions.prepara_transition(settings, r.varieta_public_id, r.varieta_nome, r.target_state)
                proposte.append({
                    "tipo": "semina_transition", "varieta_public_id": p.varieta_public_id,
                    "semina_public_id": p.semina_public_id, "varieta_nome": p.varieta_nome,
                    "stato_attuale": p.stato_attuale,
                    "passi": [passo.stato for passo in p.passi],
                })
        except (actions.PropostaAmbigua, actions.SeminaNonTrovata) as exc:
            errori.append(str(exc))
    return JSONResponse({"proposte": proposte, "errori": errori})


@app.post("/api/conferma")
def conferma(body: dict, attore: str = Depends(richiedi_autenticazione)) -> JSONResponse:
    proposta = body.get("proposta") or {}
    settings = _settings()
    try:
        if proposta.get("tipo") == "semina_commission":
            p = actions.PropostaCommission(
                varieta_public_id=proposta["varieta_public_id"], varieta_nome=proposta["varieta_nome"],
                lotto_seme_public_id=proposta["lotto_seme_public_id"],
                protocollo_versione_public_id=proposta["protocollo_versione_public_id"],
                grammi=proposta["grammi"], num_set=proposta["num_set"],
                physical_started_at=proposta["physical_started_at"], origin=proposta["origin"],
                residuo_dopo=proposta["residuo_dopo"],
            )
            esito = actions.esegui_commission(settings, p, ACTOR)
        elif proposta.get("tipo") == "semina_transition":
            p = actions.PropostaTransition(
                varieta_public_id=proposta["varieta_public_id"],
                semina_public_id=proposta["semina_public_id"], varieta_nome=proposta["varieta_nome"],
                stato_attuale=proposta["stato_attuale"],
                passi=[actions.PassoTransizione(stato=s) for s in proposta["passi"]],
            )
            esito = actions.esegui_transition(settings, p, ACTOR)
        else:
            raise HTTPException(400, "Tipo di proposta non riconosciuto.")
    except (actions.PropostaAmbigua, actions.SeminaNonTrovata, actions.SeminaOperazioneFallita) as exc:
        return JSONResponse({"ok": False, "messaggio": str(exc)}, status_code=409)
    except KeyError as exc:
        raise HTTPException(400, f"Proposta incompleta: manca {exc}.")
    return JSONResponse({"ok": True, "messaggio": esito})


@app.get("/api/salute")
def salute(_: str = Depends(richiedi_autenticazione)) -> dict:
    """Verifica rapida che il servizio possa leggere il database reale,
    senza scrivere nulla -- utile subito dopo il deploy su Render."""
    settings = _settings()
    varieta = db_context.elenca_varieta(settings)
    return {"ok": True, "varieta_nel_sistema": len(varieta)}
