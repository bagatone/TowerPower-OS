"""Interpretazione in linguaggio naturale -> proposta strutturata.

Non scrive mai nulla: restituisce solo dati per popolare una proposta
che l'utente deve confermare (actions.py fa poi una sua rilettura live
indipendente prima di eseguire per davvero -- questo modulo e' solo un
suggerimento, mai l'origine di verita' su un identificativo).

Se il modello non e' sicuro di quale varietà/lotto/stato intendere,
deve rispondere con `azione="chiarimento"` invece di indovinare -- e'
imposto nel prompt di sistema, non lasciato all'iniziativa del modello.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import anthropic

from . import db_context
from ..infrastructure.postgresql.settings import PostgreSQLSettings

MODEL = os.environ.get("DIARIO_MODEL", "claude-sonnet-4-5")

STATI_VALIDI = ["AVVIATA", "GERMINAZIONE", "LUCE", "CRESCITA", "PRONTA_ALLA_RACCOLTA", "CHIUSA"]
ORIGINI_VALIDE = ["PIANO_PRODUZIONE", "ORDINE_CLIENTE", "RIPRISTINO_STOCK"]

_TOOL = {
    "name": "interpreta_diario",
    "description": "Traduce una frase in italiano sugli eventi di campo in una o più richieste "
                    "strutturate per il sistema TPO. Non eseguire nulla: solo interpretare.",
    "input_schema": {
        "type": "object",
        "properties": {
            "richieste": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "azione": {
                            "type": "string",
                            "enum": ["semina_commission", "semina_transition", "chiarimento"],
                        },
                        "varieta_public_id": {
                            "type": ["string", "null"],
                            "description": "public_id esatto (es. VAR-000004), solo dal contesto fornito, "
                                            "mai inventato. null se non identificabile con certezza.",
                        },
                        "semina_public_id": {
                            "type": ["string", "null"],
                            "description": "solo per semina_transition: public_id esatto della semina "
                                            "(es. SEM-000007), SOLO se l'utente lo ha scritto esplicitamente "
                                            "nel testo, copiato carattere per carattere. null se l'utente non "
                                            "ha specificato un codice semina -- in quel caso il sistema lo "
                                            "determina da solo dalla varietà.",
                        },
                        "num_set": {
                            "type": ["string", "null"],
                            "description": "solo per semina_commission: numero di SET seminati, come stringa.",
                        },
                        "origin": {
                            "type": ["string", "null"],
                            "enum": ORIGINI_VALIDE + [None],
                            "description": "solo per semina_commission. Se non specificato dall'utente, "
                                            "usa RIPRISTINO_STOCK (è l'origine quasi sempre usata finora).",
                        },
                        "physical_started_at": {
                            "type": ["string", "null"],
                            "description": "solo per semina_commission, ISO8601 con offset, SOLO se l'utente "
                                            "ha indicato esplicitamente data/ora; altrimenti null (si userà ora).",
                        },
                        "target_state": {
                            "type": ["string", "null"],
                            "enum": STATI_VALIDI + [None],
                            "description": "solo per semina_transition.",
                        },
                        "chiarimento": {
                            "type": ["string", "null"],
                            "description": "solo per azione=chiarimento: cosa manca per procedere, in italiano.",
                        },
                    },
                    "required": ["azione"],
                },
            }
        },
        "required": ["richieste"],
    },
}


@dataclass(frozen=True)
class RichiestaInterpretata:
    azione: str
    varieta_public_id: str | None
    varieta_nome: str | None
    semina_public_id: str | None
    num_set: str | None
    origin: str | None
    physical_started_at: str | None
    target_state: str | None
    chiarimento: str | None


def _prompt_sistema(varieta: list[db_context.VarietaInfo]) -> str:
    elenco = "\n".join(f"- {v.public_id}: {v.denominazione} (codice {v.codice})" for v in varieta)
    return f"""Sei l'interprete del "diario" di Tower Power, una micro-fattoria di microgreens.
Il tuo unico compito: tradurre una frase in italiano sugli eventi di campo (semine, cambi di
stadio) in richieste strutturate per il sistema TPO, usando lo strumento fornito. Non scrivi
mai nulla direttamente: la tua proposta viene sempre mostrata all'utente prima di essere
eseguita.

Varietà esistenti nel sistema (usa SEMPRE uno di questi public_id, mai un altro, mai inventato):
{elenco}

Regole stringenti:
- Se la frase nomina più varietà con la stessa azione (es. "Mizuna e Rábano passano in luce"),
  restituisci una richiesta separata per ciascuna.
- Se non riesci a far corrispondere con certezza una varietà nominata a uno dei public_id sopra,
  usa azione="chiarimento" per quella voce, non indovinare.
- Il ciclo di vita di una semina è, in ordine, sempre questi stati, uno alla volta, mai saltati:
  AVVIATA, GERMINAZIONE, LUCE, CRESCITA, PRONTA_ALLA_RACCOLTA, CHIUSA. "Passa in luce"/"in
  luce"/"fine germinazione" significa target_state=LUCE. "Pronta per la raccolta"/"pronta"
  significa target_state=PRONTA_ALLA_RACCOLTA. "Germinazione"/"germinata" significa
  target_state=GERMINAZIONE. "Cresciuta"/"in crescita"/"passa in crescita"/"e' cresciuta"
  significa target_state=CRESCITA -- usa questa parola con fiducia anche se la semina e'
  ancora a GERMINAZIONE o non ancora a LUCE: non calcolare tu quali passi intermedi
  servono (es. LUCE prima di CRESCITA), basta il target_state finale richiesto, il
  sistema calcola da solo i passaggi mancanti e li mostra tutti all'utente prima di
  eseguire.
- Se l'utente scrive esplicitamente il codice di una semina (es. "SEM-000007"), riportalo in
  semina_public_id esattamente come scritto, in maiuscolo. Se non lo scrive, lascia
  semina_public_id=null: il sistema lo determina da solo dalla varietà, e se ce ne fosse più di
  una attiva chiederà lui stesso di specificare.
- "Seminato N set di X" è sempre semina_commission con quella varietà e quel num_set.
- Se manca un'informazione essenziale per semina_commission (numero di SET), usa
  azione="chiarimento" per quella voce.
- Non decidere mai tu il lotto di seme o il protocollo da usare: il sistema li determina da solo
  a partire dalla varietà.
"""


def interpreta(testo: str, settings: PostgreSQLSettings) -> list[RichiestaInterpretata]:
    varieta = db_context.elenca_varieta(settings)
    by_id = {v.public_id: v for v in varieta}
    client = anthropic.Anthropic()
    risposta = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=_prompt_sistema(varieta),
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "interpreta_diario"},
        messages=[{"role": "user", "content": testo}],
    )
    blocco = next((b for b in risposta.content if b.type == "tool_use"), None)
    if blocco is None:
        return [RichiestaInterpretata(
            azione="chiarimento", varieta_public_id=None, varieta_nome=None, semina_public_id=None,
            num_set=None, origin=None, physical_started_at=None, target_state=None,
            chiarimento="Non sono riuscito a interpretare la richiesta, riprova riformulando.",
        )]
    risultati = []
    for r in blocco.input.get("richieste", []):
        vid = r.get("varieta_public_id")
        nome = by_id[vid].denominazione if vid in by_id else None
        if r.get("azione") != "chiarimento" and vid not in by_id:
            risultati.append(RichiestaInterpretata(
                azione="chiarimento", varieta_public_id=None, varieta_nome=None, semina_public_id=None,
                num_set=None, origin=None, physical_started_at=None, target_state=None,
                chiarimento=f"Varietà non riconosciuta con certezza in: {testo!r}",
            ))
            continue
        risultati.append(RichiestaInterpretata(
            azione=r.get("azione"), varieta_public_id=vid, varieta_nome=nome,
            semina_public_id=r.get("semina_public_id"),
            num_set=r.get("num_set"), origin=r.get("origin") or "RIPRISTINO_STOCK",
            physical_started_at=r.get("physical_started_at"), target_state=r.get("target_state"),
            chiarimento=r.get("chiarimento"),
        ))
    return risultati
