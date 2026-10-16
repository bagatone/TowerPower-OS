"""Incassi nel diario: elenco "da incassare" (sola lettura) e registrazione del
pagamento di una o piu' consegne (scrittura SOLO dopo conferma a schermo).

Perimetro approvato da Matteo il 16/10/2026 come D6 dell'addendum di governance
(docs/architecture/DIARIO_PAGAMENTI_ADDENDUM.md): il diario puo' registrare
`pagamento-consegna registra`, mai l'annullo di un pagamento (resta da terminale)
e mai fatture. Stesse garanzie delle semine:

- ogni consegna usata per scrivere viene RILETTA dal database un istante prima
  di scrivere (stato CONSEGNATA, non gia' pagata, numero di tentativo per la
  chiave di idempotenza), mai riusata da una proposta precedente;
- l'esecuzione passa sempre da `run_pagamento_consegna_command`, lo stesso
  adapter CLI gia' testato: nessuna regola di dominio duplicata qui;
- il metodo di pagamento non si indovina mai: se manca, si chiede;
- l'importo e' facoltativo e solo per una consegna (come nello script).

Limite noto: le bolle PDF NON si rigenerano da qui (il servizio gira su Render,
le bolle stanno sul Mac). Il messaggio di esito stampa il comando da lanciare.
"""
from __future__ import annotations

import io
from argparse import Namespace
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from ..cli.pagamento_consegna import run_pagamento_consegna_command
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from . import db_context

TZ_CANARIE = timezone(timedelta(hours=1))
METODI = ("BONIFICO", "CONTANTI", "CARTA", "BIZUM", "ALTRO")
SCRIPT_PAGAMENTI = "scripts/commissioning/2026-10-11_pagamenti_consegne.py"


class PagamentoNonPossibile(Exception):
    """La proposta non e' formulabile (consegna inesistente, gia' pagata, metodo mancante...)."""


class PagamentoFallito(Exception):
    pass


_SQL_NON_PAGATE = """
SELECT c.id, c.public_id, cl.public_id, cl.denominazione, c.data_effettiva
FROM tpo.consegne c JOIN tpo.clienti cl ON cl.id=c.cliente_id
WHERE c.stato='CONSEGNATA'
  AND NOT EXISTS (SELECT 1 FROM tpo.pagamenti_consegna p
                  WHERE p.consegna_id=c.id AND p.tipo='PAGAMENTO'
                    AND NOT EXISTS (SELECT 1 FROM tpo.pagamenti_consegna a WHERE a.annulla_pagamento_id=p.id))
ORDER BY c.data_effettiva, c.public_id"""
_SQL_VOCI = """
SELECT rc.consegna_id, v.denominazione, rc.quantita, rc.unita_misura::text
FROM tpo.righe_consegna rc JOIN tpo.varieta v ON v.id=rc.varieta_id
WHERE rc.consegna_id = ANY(%s) AND rc.rettifica_riga_consegna_id IS NULL
ORDER BY rc.consegna_id, rc.posizione"""
_SQL_STATO = """
SELECT c.public_id, c.stato::text, cl.denominazione, c.data_effettiva,
       (SELECT count(*) FROM tpo.pagamenti_consegna p WHERE p.consegna_id=c.id AND p.tipo='PAGAMENTO'),
       EXISTS (SELECT 1 FROM tpo.pagamenti_consegna p
               WHERE p.consegna_id=c.id AND p.tipo='PAGAMENTO'
                 AND NOT EXISTS (SELECT 1 FROM tpo.pagamenti_consegna a WHERE a.annulla_pagamento_id=p.id))
FROM tpo.consegne c JOIN tpo.clienti cl ON cl.id=c.cliente_id
WHERE c.public_id = ANY(%s)"""


@dataclass(frozen=True)
class ConsegnaDaIncassare:
    codice: str
    data: str            # AAAA-MM-GG, giorno di consegna (fuso Canarie)
    giorni: int
    voci: list[str]


@dataclass(frozen=True)
class ClienteDaIncassare:
    cliente_public_id: str
    cliente_nome: str
    consegne: list[ConsegnaDaIncassare]


@dataclass(frozen=True)
class PropostaPagamento:
    consegne: list[dict]         # [{"codice", "data", "voci"}] come mostrate all'utente
    cliente_nome: str
    metodo: str
    data_pagamento: str          # AAAA-MM-GG
    importo: str | None
    tipo: str = field(default="pagamento_consegna", init=False)


def oggi_canarie(adesso: datetime | None = None) -> date:
    return (adesso or datetime.now(TZ_CANARIE)).astimezone(TZ_CANARIE).date()


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


# --- lettura -----------------------------------------------------------------

def leggi_da_incassare(cur, oggi: date | None = None) -> list[ClienteDaIncassare]:
    """Clienti con consegne effettuate e non pagate; prima il cliente con la consegna piu' vecchia."""
    oggi = oggi or oggi_canarie()
    cur.execute(_SQL_NON_PAGATE)
    consegne = cur.fetchall()
    if not consegne:
        return []
    voci: dict[int, list[str]] = defaultdict(list)
    cur.execute(_SQL_VOCI, ([r[0] for r in consegne],))
    for cons_pk, nome, quantita, unita in cur.fetchall():
        voci[cons_pk].append(f"{nome} {_n(quantita)} {unita}")
    per_cliente: dict[str, list[ConsegnaDaIncassare]] = {}
    nomi: dict[str, str] = {}
    for pk, codice, cli_pid, cli_nome, effettiva in consegne:
        giorno = effettiva.astimezone(TZ_CANARIE).date()
        per_cliente.setdefault(cli_pid, []).append(ConsegnaDaIncassare(
            codice=codice, data=giorno.isoformat(), giorni=(oggi - giorno).days, voci=voci.get(pk, [])))
        nomi[cli_pid] = cli_nome
    elenco = [ClienteDaIncassare(cli, nomi[cli], c) for cli, c in per_cliente.items()]
    return sorted(elenco, key=lambda e: (e.consegne[0].data, e.cliente_nome))


def da_incassare(settings: PostgreSQLSettings, oggi: date | None = None) -> list[ClienteDaIncassare]:
    with db_context._connect(settings) as conn, conn.cursor() as cur:
        return leggi_da_incassare(cur, oggi)


def _stato_consegne(cur, codici: list[str]) -> dict[str, dict]:
    cur.execute(_SQL_STATO, (codici,))
    return {
        r[0]: {"stato": r[1], "cliente": r[2], "effettiva": r[3], "n_prec": int(r[4]), "pagata": bool(r[5])}
        for r in cur.fetchall()
    }


# --- proposta (nessuna scrittura) --------------------------------------------

def prepara_pagamento(
    settings: PostgreSQLSettings, codici: list[str], metodo: str | None,
    data_pagamento: str | None = None, importo: str | None = None, oggi: date | None = None,
) -> PropostaPagamento:
    codici = list(dict.fromkeys(c.strip().upper() for c in codici if c and c.strip()))
    if not codici:
        raise PagamentoNonPossibile("Nessuna consegna indicata.")
    metodo = (metodo or "").strip().upper()
    if not metodo:
        raise PagamentoNonPossibile(
            "Manca il metodo di pagamento (" + ", ".join(METODI) + "): non lo scelgo io.")
    if metodo not in METODI:
        raise PagamentoNonPossibile(f"Metodo '{metodo}' non valido ({', '.join(METODI)}).")
    oggi = oggi or oggi_canarie()
    if data_pagamento:
        try:
            giorno = date.fromisoformat(data_pagamento)
        except ValueError:
            raise PagamentoNonPossibile(f"Data '{data_pagamento}' non valida (serve AAAA-MM-GG).") from None
        if giorno > oggi:
            raise PagamentoNonPossibile(f"La data del pagamento ({giorno.isoformat()}) e' nel futuro.")
    else:
        giorno = oggi
    if importo not in (None, ""):
        if len(codici) != 1:
            raise PagamentoNonPossibile("L'importo si indica solo con una consegna.")
        try:
            if Decimal(str(importo)) < 0:
                raise InvalidOperation
        except InvalidOperation:
            raise PagamentoNonPossibile(f"Importo '{importo}' non valido.") from None
        importo = str(importo)
    else:
        importo = None

    with db_context._connect(settings) as conn, conn.cursor() as cur:
        stato = _stato_consegne(cur, codici)
        ignote = [c for c in codici if c not in stato]
        if ignote:
            raise PagamentoNonPossibile("Consegne inesistenti: " + ", ".join(ignote) + ".")
        non_fatte = [c for c in codici if stato[c]["stato"] != "CONSEGNATA"]
        if non_fatte:
            raise PagamentoNonPossibile("Consegne non ancora effettuate: " + ", ".join(non_fatte) + ".")
        gia = [c for c in codici if stato[c]["pagata"]]
        if gia:
            raise PagamentoNonPossibile("Gia' pagate: " + ", ".join(gia) + ".")
        clienti = {stato[c]["cliente"] for c in codici}
        if len(clienti) != 1:
            raise PagamentoNonPossibile(
                "Le consegne sono di clienti diversi (" + ", ".join(sorted(clienti)) + "): una richiesta per cliente.")
        for codice in codici:
            if stato[codice]["effettiva"].astimezone(TZ_CANARIE).date() > giorno:
                raise PagamentoNonPossibile(
                    f"{codice} e' stata consegnata dopo la data di pagamento {giorno.isoformat()}.")
        cur.execute("SELECT id, public_id FROM tpo.consegne WHERE public_id = ANY(%s)", (codici,))
        pk = {pid: i for i, pid in cur.fetchall()}
        cur.execute(_SQL_VOCI, ([pk[c] for c in codici],))
        voci: dict[int, list[str]] = defaultdict(list)
        for cons_pk, nome, quantita, unita in cur.fetchall():
            voci[cons_pk].append(f"{nome} {_n(quantita)} {unita}")
    return PropostaPagamento(
        consegne=[{"codice": c, "data": stato[c]["effettiva"].astimezone(TZ_CANARIE).date().isoformat(),
                   "voci": voci.get(pk[c], [])} for c in codici],
        cliente_nome=clienti.pop(), metodo=metodo, data_pagamento=giorno.isoformat(), importo=importo,
    )


# --- esecuzione (SOLO dopo conferma) -----------------------------------------

def esegui_pagamento(
    settings: PostgreSQLSettings, proposta: PropostaPagamento, actor: str,
    runner=run_pagamento_consegna_command,
) -> str:
    codici = [c["codice"] for c in proposta.consegne]
    righe_esito: list[str] = []
    registrate: list[str] = []
    for codice in codici:
        # Rilettura live PRIMA di ogni consegna: stato e numero di tentativo non vengono mai
        # dalla proposta, che puo' essere vecchia di minuti (o gia' eseguita da un altro telefono).
        with db_context._connect(settings) as conn, conn.cursor() as cur:
            stato = _stato_consegne(cur, [codice]).get(codice)
        if stato is None or stato["stato"] != "CONSEGNATA":
            raise PagamentoFallito(_con_parziale(righe_esito, f"{codice}: non e' una consegna effettuata."))
        if stato["pagata"]:
            righe_esito.append(f"{codice}: gia' pagata, saltata.")
            continue
        chiave = f"diario-pagamento-{codice.lower()}-n{stato['n_prec'] + 1}"
        args = Namespace(
            pagamento_consegna_command="registra", consegna=codice, data=proposta.data_pagamento,
            metodo=proposta.metodo, importo=proposta.importo, note=None, storico=False, actor=actor,
            reason=f"Pagamento consegna {codice} ({proposta.cliente_nome}) registrato tramite il diario.",
            correlation_id=chiave, idempotency_key=chiave,
        )
        stdout, stderr = io.StringIO(), io.StringIO()
        exit_code = runner(args, stdout=stdout, stderr=stderr)
        if exit_code != 0:
            motivo = (stderr.getvalue() or stdout.getvalue()).strip() or f"Fallito (codice {exit_code})."
            raise PagamentoFallito(_con_parziale(righe_esito, f"{codice}: {motivo}"))
        pid = next((r.split("=", 1)[1] for r in stdout.getvalue().splitlines()
                    if r.startswith("PAGAMENTO_CONSEGNA_ID=")), "?")
        righe_esito.append(f"{codice}: pagamento {pid} registrato ({proposta.metodo}, {proposta.data_pagamento}).")
        registrate.append(codice)
    if registrate:
        righe_esito.append(
            "Le bolle PDF non si rigenerano da qui. Per averle con PAGADO, dal Mac:\n"
            f"  .venv/bin/python {SCRIPT_PAGAMENTI} --pagata {' '.join(codici)} --metodo {proposta.metodo} --esegui\n"
            "(le consegne gia' pagate vengono saltate, le bolle rigenerate)")
    return "\n".join(righe_esito)


def _con_parziale(fatte: list[str], errore: str) -> str:
    if not fatte:
        return errore + " Nulla e' stato registrato."
    return "\n".join(fatte) + "\nPOI: " + errore + " Le consegne rimaste non sono state registrate."
