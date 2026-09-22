"""Autenticazione minima ma obbligatoria (condizione 1 dell'addendum di
governance): password condivisa, mai nel codice, letta solo da variabile
d'ambiente impostata su Render. HTTP Basic Auth -- semplice, sufficiente
per un solo servizio a uso interno con un numero ridotto di persone, e
supportato nativamente dal browser senza bisogno di una pagina di login
separata."""
from __future__ import annotations

import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

_security = HTTPBasic()


def _password_attesa() -> str:
    valore = os.environ.get("DIARIO_PASSWORD")
    if not valore:
        raise RuntimeError(
            "DIARIO_PASSWORD non impostata: il servizio non deve partire senza, "
            "vedi handoff/diario-governance-addendum.md, condizione 1."
        )
    return valore


def richiedi_autenticazione(credenziali: HTTPBasicCredentials = Depends(_security)) -> str:
    attesa = _password_attesa()
    corretta = secrets.compare_digest(credenziali.password, attesa)
    if not corretta:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password non corretta.",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credenziali.username or "diario"
