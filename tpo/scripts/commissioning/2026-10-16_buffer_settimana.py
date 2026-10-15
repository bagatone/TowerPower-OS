"""SOLA LETTURA - SCORTA SETTIMANALE per le varieta' ad ALTO CONSUMO: quanto seminare in piu' (16/10/2026).

Principio di Matteo: si puo' sempre produrre PIU' di quanto c'e' in programma, e per le varieta' molto consumate si
produce sempre qualcosa in piu' piuttosto che in meno. Il motore di pianificazione calcola il buffer per riga d'ordine
(e' congelato), quindi la scorta e' una tua scelta: questo report ti dice QUANTO seminare in piu'. Le semine extra le
registri come sempre (semina senza cliente: 2026-10-12_semine.py): da quel momento il sistema le vede "in campo", poi
a magazzino dopo la raccolta, e questo report le sottrae da solo.

ALTO CONSUMO = varieta' consegnate in media almeno --soglia SET a settimana nelle ultime 4 settimane (default 2; con
--soglia 0 la scorta vale per tutte le varieta'); oppure scegli tu: --alto-consumo Afila Cilantro Rabano.
La scorta (--scorta, default 1 SET a settimana) vale solo per quelle; per le altre vale 0.

Per ogni varieta' con protocollo approvato corrente e per ognuna delle prossime N settimane (sett. 1 = oggi..oggi+6):
  serve  = ordini aperti con consegna in quella settimana (residuo non ancora consegnato; scaduti -> sett. 1) + scorta
  arriva = sett. 1: giacenza di magazzino + semine in campo la cui finestra di raccolta inizia entro la sett. 1;
           sett. k: semine in campo la cui finestra di raccolta inizia nella sett. k  (resa attesa - raccolto)
  manca  = max(0, serve - arriva)
ASSUNZIONE (microgreens = deperibili): l'eccedenza di una settimana NON copre la successiva, il magazzino conta solo per
la sett. 1: "manca" e' prudente, cioe' in eccesso, in linea con "meglio di piu' che di meno".
Una semina di OGGI e' pronta tra `ciclo` giorni (dal protocollo): copre la settimana in cui cade quella data. Il report
dice quanti SET seminare OGGI per coprire quella settimana (diviso per la resa del protocollo e arrotondato PER ECCESSO
alla granularita' produttiva) e segnala le settimane precedenti con un "manca" che una semina di oggi non puo' piu' coprire.
NON conta: piani non ancora seminati, semine con resa attesa non compilata (le elenca), consegne oltre l'orizzonte.

Non scrive nulla. Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-16_buffer_settimana.py
  .venv/bin/python scripts/commissioning/2026-10-16_buffer_settimana.py --alto-consumo Afila Cilantro --scorta 1
  .venv/bin/python scripts/commissioning/2026-10-16_buffer_settimana.py --soglia 3 --settimane 4 --solo-con-domanda
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

TIMEZONE = ZoneInfo("Atlantic/Canary")
ZERO = Decimal(0)

SQL_PROTOCOLLI = """
SELECT v.id, v.denominazione, pv.ciclo_produttivo_nominale_giorni, pv.resa_attesa, pv.granularita_produttiva
FROM tpo.protocollo_versioni pv
JOIN tpo.protocolli p ON p.id = pv.protocollo_id
JOIN tpo.cultivar_usi cu ON cu.id = p.cultivar_uso_id
JOIN tpo.cultivar c ON c.id = cu.cultivar_id
JOIN tpo.varieta v ON v.id = c.varieta_id
JOIN tpo.usi_produttivi up ON up.id = cu.uso_produttivo_id AND up.codice = 'MICROGREEN'
WHERE pv.stato_approvazione = 'APPROVATA' AND pv.valida_al IS NULL AND pv.resa_unita_misura = 'SET'
ORDER BY v.denominazione"""
SQL_DOMANDA = """
SELECT ro.varieta_id, o.data_consegna_prevista,
       ro.quantita - COALESCE((SELECT SUM(rc.quantita) FROM tpo.righe_consegna rc JOIN tpo.consegne c ON c.id=rc.consegna_id
                               WHERE rc.riga_ordine_id=ro.id AND c.stato='CONSEGNATA'),0)
FROM tpo.righe_ordine ro JOIN tpo.ordini o ON o.id=ro.ordine_id
WHERE o.stato IN ('APERTO','PARZIALMENTE_EVASO') AND ro.unita_misura='SET'"""
SQL_CONSUMO = """
SELECT rc.varieta_id, SUM(rc.quantita)
FROM tpo.righe_consegna rc JOIN tpo.consegne c ON c.id=rc.consegna_id
WHERE c.stato='CONSEGNATA' AND rc.unita_misura='SET' AND rc.rettifica_riga_consegna_id IS NULL
  AND c.data_effettiva >= %s
GROUP BY rc.varieta_id"""
SQL_STOCK = "SELECT varieta_id, disponibile FROM tpo.stock WHERE unita_misura='SET'"
SQL_SEMINE = """
SELECT s.varieta_id, s.public_id, s.codice_tracciabilita, s.stato::text, s.expected_useful_quantity,
       s.expected_useful_uom::text, s.harvest_window_start,
       COALESCE((SELECT SUM(rc.quantita) FROM tpo.raccolte rc WHERE rc.semina_id=s.id AND rc.unita_misura='SET'),0)
FROM tpo.semine s WHERE s.stato<>'CHIUSA'"""


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f") if value else "0"


def settimana(giorno: date, oggi: date, n: int) -> int | None:
    """Indice 1..n della settimana (sett. 1 = oggi..oggi+6); i giorni passati cadono nella 1, oltre l'orizzonte None."""
    if giorno <= oggi:
        return 1
    k = (giorno - oggi).days // 7 + 1
    return k if k <= n else None


def leggi(conn, oggi: date, n: int):
    cur = conn.cursor()
    cur.execute(SQL_PROTOCOLLI)
    protocolli = {r[0]: {"nome": r[1], "ciclo": int(r[2]) if r[2] is not None else None, "resa": Decimal(r[3]),
                         "gran": Decimal(r[4])} for r in cur.fetchall()}
    domanda: dict[int, dict[int, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    cur.execute(SQL_DOMANDA)
    for var_id, data, residuo in cur.fetchall():
        k = settimana(data, oggi, n)
        if k is not None and Decimal(residuo) > 0:
            domanda[var_id][k] += Decimal(residuo)
    cur.execute(SQL_CONSUMO, (datetime.combine(oggi - timedelta(days=28), datetime.min.time(), TIMEZONE),))
    consumo = {var_id: Decimal(q) / 4 for var_id, q in cur.fetchall()}        # SET a settimana, media delle ultime 4
    cur.execute(SQL_STOCK)
    stock = defaultdict(Decimal)
    for var_id, disp in cur.fetchall():
        stock[var_id] += Decimal(disp)
    arriva: dict[int, dict[int, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    non_compilate: dict[int, list[str]] = defaultdict(list)
    cur.execute(SQL_SEMINE)
    for var_id, pid, codice, stato, atteso, uom, finestra, raccolto in cur.fetchall():
        if atteso is None or uom != "SET":
            non_compilate[var_id].append(f"{pid} {codice or 'senza codice'}")
            continue
        residuo = max(Decimal(atteso) - Decimal(raccolto), ZERO)
        if residuo <= 0:
            continue
        k = settimana(finestra.astimezone(TIMEZONE).date(), oggi, n)
        if k is not None:
            arriva[var_id][k] += residuo
    return protocolli, domanda, stock, arriva, non_compilate, consumo


def analizza(proto, domanda, stock, arriva, oggi: date, n: int, buffer: Decimal):
    """Righe per settimana e suggerimento di semina di oggi per UNA varieta'."""
    righe = []
    for k in range(1, n + 1):
        ordini = domanda.get(k, ZERO)
        serve = ordini + buffer
        mag = stock if k == 1 else ZERO
        campo = arriva.get(k, ZERO)
        manca = max(serve - mag - campo, ZERO)
        righe.append({"k": k, "ordini": ordini, "serve": serve, "mag": mag, "campo": campo, "manca": manca})
    atterra = oggi + timedelta(days=proto["ciclo"]) if proto["ciclo"] is not None else None
    k_semina = settimana(atterra, oggi, n) if atterra else None
    seminare = ZERO
    if k_semina is not None:
        utile = righe[k_semina - 1]["manca"]
        if utile > 0:
            seminati = utile / proto["resa"]
            seminare = (seminati / proto["gran"]).to_integral_value(rounding=ROUND_CEILING) * proto["gran"]
    tardi = [r["k"] for r in righe if r["manca"] > 0 and (k_semina is None or r["k"] < k_semina)]
    return righe, atterra, k_semina, seminare, tardi


def alto_consumo(protocolli, consumo, soglia: Decimal, scelte: list[str] | None):
    """Insieme degli id varieta' ad alto consumo: scelti a mano (per nome) oppure oltre la soglia."""
    if scelte:
        voluti = {_fold(x) for x in scelte}
        trovati = {vid for vid, p in protocolli.items() if _fold(p["nome"]) in voluti}
        mancanti = voluti - {_fold(protocolli[v]["nome"]) for v in trovati}
        return trovati, sorted(mancanti)
    return {vid for vid in protocolli if consumo.get(vid, ZERO) >= soglia}, []


def _fold(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn").strip()


def run(conn, settimane: int = 3, scorta: Decimal = Decimal(1), soglia: Decimal = Decimal(2),
        scelte: list[str] | None = None, solo_con_domanda: bool = False,
        oggi: date | None = None, out=print) -> int:
    oggi = oggi or datetime.now(TIMEZONE).date()
    protocolli, domanda, stock, arriva, non_compilate, consumo = leggi(conn, oggi, settimane)
    alti, mancanti = alto_consumo(protocolli, consumo, soglia, scelte)
    if mancanti:
        out(f"STOP: varieta' sconosciute o senza protocollo approvato: {', '.join(mancanti)}.")
        return 2
    out(f"== SCORTA SETTIMANALE +{_n(scorta)} SET per le varieta' ad alto consumo - oggi {oggi.isoformat()}, "
        f"{settimane} settimane (SOLA LETTURA)")
    for k in range(1, settimane + 1):
        a = oggi + timedelta(days=7 * (k - 1))
        out(f"   sett. {k}: {a:%d/%m} - {a + timedelta(days=6):%d/%m}")
    if scelte:
        out("   Alto consumo (scelto da te): " + ", ".join(sorted(protocolli[v]["nome"] for v in alti)))
    else:
        elenco = sorted(((protocolli[v]["nome"], consumo.get(v, ZERO)) for v in alti), key=lambda x: -x[1])
        out(f"   Alto consumo (>= {_n(soglia)} SET/sett., media delle ultime 4 settimane): "
            + (", ".join(f"{n} {format(c, '.1f')}" for n, c in elenco) or "nessuna"))
    out("   Assunzione: il fresco non si accumula (l'eccedenza di una settimana non copre la successiva); il magazzino conta "
        "solo per la sett. 1.")
    totale = []
    mostrate = 0
    for var_id, proto in sorted(protocolli.items(), key=lambda kv: kv[1]["nome"]):
        buffer = scorta if var_id in alti else ZERO
        righe, atterra, k_semina, seminare, tardi = analizza(
            proto, domanda.get(var_id, {}), stock.get(var_id, ZERO), arriva.get(var_id, {}), oggi, settimane, buffer)
        if solo_con_domanda and not any(r["ordini"] for r in righe) and not buffer:
            continue
        if not buffer and not any(r["ordini"] or r["campo"] for r in righe) and not stock.get(var_id, ZERO):
            continue
        mostrate += 1
        ciclo = f"ciclo {proto['ciclo']} gg, semina di oggi pronta il {atterra:%d/%m} (sett. {k_semina or 'oltre'})" \
            if atterra else "ciclo non noto"
        etichetta = f"ALTO CONSUMO {format(consumo.get(var_id, ZERO), '.1f')}/sett., scorta +{_n(buffer)}" if buffer \
            else f"consumo {format(consumo.get(var_id, ZERO), '.1f')}/sett., senza scorta"
        out(f"\n{proto['nome']}  [{etichetta}]  ({ciclo}; resa {_n(proto['resa'])}, granularita' {_n(proto['gran'])})")
        out("   sett. | ordini | +scorta = serve | magazzino | campo | manca")
        for r in righe:
            out(f"   {r['k']:>5} | {_n(r['ordini']):>6} | {_n(buffer):>6} = {_n(r['serve']):<6} | {_n(r['mag']):>9} | "
                f"{_n(r['campo']):>5} | {_n(r['manca']):>5}")
        if non_compilate.get(var_id):
            out("   ATTENZIONE: semine in campo con resa attesa NON compilata (non contate): "
                + ", ".join(non_compilate[var_id]))
        if seminare > 0:
            out(f"   -> SEMINA OGGI: {_n(seminare)} SET (copre la sett. {k_semina}: manca {_n(righe[k_semina - 1]['manca'])})")
            totale.append((proto["nome"], seminare))
        else:
            out("   -> niente da seminare oggi" + (f" per la sett. {k_semina}" if k_semina else ""))
        if tardi:
            out("   ATTENZIONE: manca anche in sett. " + ", ".join(str(k) for k in tardi)
                + ": una semina di oggi arriva dopo (serve magazzino, altre semine o ridurre la scorta)")
    senza_protocollo = sorted({v for v in set(domanda) - set(protocolli)})
    if senza_protocollo:
        cur = conn.cursor()
        cur.execute("SELECT denominazione FROM tpo.varieta WHERE id = ANY(%s) ORDER BY denominazione", (senza_protocollo,))
        out("\nATTENZIONE: ordini aperti per varieta' SENZA protocollo approvato (non valutabili): "
            + ", ".join(r[0] for r in cur.fetchall()))
    out("\n== RIEPILOGO: SEMINA OGGI (SET in piu' rispetto a quanto gia' in campo)")
    if totale:
        for nome, q in totale:
            out(f"   {nome}: {_n(q)}")
        out(f"   Totale: {_n(sum((q for _, q in totale), ZERO))} SET")
    else:
        out("   niente: ordini e scorta sono coperti per la settimana in cui cade una semina di oggi.")
    out("   Per registrare una semina extra (anche di una varieta' non in programma, senza cliente): "
        ".venv/bin/python scripts/commissioning/2026-10-12_semine.py --riga \"Afila:1\" --giorno AAAA-MM-GG --ora 09:00")
    if not mostrate:
        out("(nessuna varieta' da mostrare)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scorta", default="1", help="SET di scorta a settimana per le varieta' ad alto consumo (default 1)")
    ap.add_argument("--soglia", default="2", help="SET/settimana (media 4 settimane) da cui una varieta' e' ad alto consumo (default 2; 0 = tutte)")
    ap.add_argument("--alto-consumo", nargs="+", metavar="VARIETA", help="sceglie tu le varieta' ad alto consumo")
    ap.add_argument("--settimane", type=int, default=3, help="orizzonte in settimane (default 3)")
    ap.add_argument("--solo-con-domanda", action="store_true", help="solo le varieta' con ordini aperti nell'orizzonte")
    a = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"], autocommit=True)
    conn.read_only = True
    try:
        return run(conn, a.settimane, Decimal(a.scorta.replace(",", ".")), Decimal(a.soglia.replace(",", ".")),
                   a.alto_consumo, a.solo_con_domanda)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
