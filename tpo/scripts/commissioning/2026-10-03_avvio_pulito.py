"""Avvio pulito del 3/10/2026 -- stato reale di Matteo, passo per passo.

Decisione di Matteo (3/10/2026): le vendite storiche non registrate non si
ricostruiscono ("non posso risalire a tutti i lotti venduti"): si riparte da cio'
che esiste adesso, e da ora ogni bolla ha un ORDINE assegnato.

Uso (dalla cartella del progetto):
    .venv/bin/python scripts/commissioning/2026-10-03_avvio_pulito.py --fase 1            # solo anteprima
    .venv/bin/python scripts/commissioning/2026-10-03_avvio_pulito.py --fase 1 --esegui   # scrive davvero

Senza --esegui NON scrive nulla: stampa i comandi `tpo` che lancerebbe, nell'ordine,
con lo stato attuale letto dal database. Con --esegui lancia i comandi governati
(ognuno con --confirm) e si ferma al primo errore. Ogni fase e' rilanciabile: legge
stato e versioni dal database, salta cio' che e' gia' stato fatto e usa
idempotency-key fisse.

Fasi:
  1  Pulizia giacenza: rettifica Afila 2 SET e Cilantro 1 SET ("vendita non registrata")
  2  Lifecycle: porta le semine allo stato fisico dichiarato da Matteo (date di comodo)
  3  Raccolte + carichi SET: Afila 2, Rabano 3, Mizuna 2, Hinojo 2, Cilantro 0.5
  4  Rettifiche vendite non registrate: Mizuna 0.5, Hinojo 0.5, Rabano 1
  5  Gustavo La Mamma: cliente, ordine manuale, consegna di stamattina, bolla PDF
  6  Bahia Real: ordine manuale per Mizuna 1 + Hinojo 1 (la consegna e' la fase 7)
  7  Bahia Real, LUNEDI': consegna con semina dichiarata per riga + bolla PDF
  8  (facoltativa) chiude SEM-000006 (Rabano 17/9, venduta): serve --esito scelto da te

Prerequisito: migrazione 0037 applicata (scripts/commissioning/migrate_to_head.sh).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters  # noqa: E402
import psycopg  # noqa: E402

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
ACTOR = "matteo"
TAG = "avvio-pulito-2026-10-03"
WORK = ROOT / "outputs" / "avvio_pulito"
PDF_DIR_DEFAULT = Path.home() / "Desktop" / "bolle"
HEAD = "20261003_0037"
CHAIN = ["AVVIATA", "GERMINAZIONE", "LUCE", "CRESCITA", "PRONTA_ALLA_RACCOLTA"]
PROV = '{"target_state":"OWNER_AUTHORIZED","effective_at":"OWNER_AUTHORIZED"}'

# --- Dati dichiarati da Matteo (3/10/2026) ----------------------------------
VAR = {"Afila": "VAR-000001", "Rabano": "VAR-000002", "Cilantro": "VAR-000003",
       "Mizuna": "VAR-000004", "Hinojo": "VAR-000005"}
PULIZIA = [  # (varieta, quantita SET, chiave)
    ("Afila", "2", "afila"), ("Cilantro", "1", "cilantro"),
]
LIFECYCLE = {  # semina -> [(stato target, istante effettivo | "avvio+N" giorni dalla semina)]
    "SEM-000004": [("PRONTA_ALLA_RACCOLTA", "2026-10-02T07:00:00+01:00")],            # Mizuna
    "SEM-000005": [("GERMINAZIONE", "avvio+0"), ("LUCE", "avvio+1"),
                   ("CRESCITA", "avvio+2"), ("PRONTA_ALLA_RACCOLTA", "2026-10-02T07:00:00+01:00")],  # Hinojo
    "SEM-000012": [("CRESCITA", "2026-10-01T07:00:00+01:00"),
                   ("PRONTA_ALLA_RACCOLTA", "2026-10-02T07:00:00+01:00")],            # Rabano 26/9
    "SEM-000008": [("CRESCITA", "2026-10-01T07:00:00+01:00"),
                   ("PRONTA_ALLA_RACCOLTA", "2026-10-03T07:00:00+01:00")],            # Cilantro 17/9
    "SEM-000009": [("GERMINAZIONE", "avvio+0"), ("LUCE", "2026-10-03T07:00:00+01:00")],  # Cilantro 29/9
    "SEM-000013": [("GERMINAZIONE", "avvio+0")],                                       # Cilantro 1/10
    "SEM-000010": [("CRESCITA", "2026-10-03T07:00:00+01:00")],                         # Afila 20/9
    "SEM-000011": [("GERMINAZIONE", "avvio+0"), ("LUCE", "2026-10-03T07:00:00+01:00")],  # Afila 29/9 (6 SET)
}
RACCOLTE = [  # (semina, SET, istante, etichetta)
    ("SEM-000002", "2", "2026-10-03T07:30:00+01:00", "Afila"),
    ("SEM-000012", "3", "2026-10-03T07:30:00+01:00", "Rabano"),
    ("SEM-000004", "2", "2026-10-02T09:00:00+01:00", "Mizuna"),
    ("SEM-000005", "2", "2026-10-02T09:00:00+01:00", "Hinojo"),
    ("SEM-000008", "0.5", "2026-10-03T07:30:00+01:00", "Cilantro"),
]
RETTIFICHE_VENDUTO = [  # (varieta, SET, semina dichiarata, istante, a chi/perche')
    ("Mizuna", "0.5", "SEM-000004", "2026-10-02T12:00:00+01:00", "mezzo SET venduto venerdi' 2/10 (Puipana/Alchimia Sushi)"),
    ("Hinojo", "0.5", "SEM-000005", "2026-10-02T12:00:00+01:00", "mezzo SET venduto venerdi' 2/10 (Puipana/Alchimia Sushi)"),
    ("Rabano", "1", "SEM-000012", "2026-10-03T08:00:00+01:00", "1 SET venduto questa settimana"),
]
GUSTAVO = "Gustavo La Mamma"
GUSTAVO_RIGHE = [("Afila", "1", "SEM-000002"), ("Rabano", "1", "SEM-000012")]
BAHIA_CLIENTE_NOME = "Hotel Secret Bahia Real"
BAHIA_ORDINE_RIGA_AFILA = ("ORD-000046", "RO-000106")
BAHIA_NUOVE = [("Mizuna", "1", "SEM-000004"), ("Hinojo", "1", "SEM-000005")]
BAHIA_PREVISTA = "2026-10-06"


# --- infrastruttura ----------------------------------------------------------
class Stop(Exception):
    pass


class Ctx:
    def __init__(self, execute: bool, pdf_dir: Path) -> None:
        self.execute = execute
        self.pdf_dir = pdf_dir
        params = load_postgresql_parameters()
        self.conn = psycopg.connect(
            host=params["host"], port=params["port"], dbname=params["dbname"],
            user=params["user"], password=params["password"], sslmode=params["sslmode"],
            connect_timeout=params["connect_timeout"], autocommit=True,
        )

    def q(self, sql: str, args: tuple = ()) -> list[tuple]:
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()

    def one(self, sql: str, args: tuple = ()):
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def tpo(self, args: list[str], label: str) -> str:
        shown = " ".join(a if re.fullmatch(r"[\w./:+=,-]+", a) else repr(a) for a in args)
        print(f"\n--- {label}\n$ tpo {shown}")
        if not self.execute:
            print("   (anteprima: non eseguito)")
            return ""
        done = subprocess.run([RUN, *args], capture_output=True, text=True)
        out = (done.stdout or "") + (done.stderr or "")
        print(out.rstrip())
        if done.returncode != 0:
            raise Stop(f"comando fallito (exit {done.returncode}): {label}")
        return done.stdout

    def check_head(self) -> None:
        rev = self.one("SELECT version_num FROM public.alembic_version")
        if not rev or rev[0] != HEAD:
            raise Stop(f"migrazione non applicata: alembic e' {rev and rev[0]}, serve {HEAD}. "
                       "Lancia prima scripts/commissioning/migrate_to_head.sh (con il tuo via libera).")


def kv(text: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}[=:]\s*(\S+)", text, re.M)
    return m.group(1) if m else None


def cliente_id(ctx: Ctx, nome: str) -> str | None:
    row = ctx.one("SELECT public_id FROM tpo.clienti WHERE denominazione=%s", (nome,))
    return row[0] if row else None


def rettifica(ctx: Ctx, varieta: str, qty: str, when: str, motivo: str, key: str,
              semina: str | None = None) -> None:
    done = ctx.one("""SELECT 1 FROM tpo.movimento_carico_requests
                      WHERE operation_scope='MOVIMENTO_RETTIFICA_GIACENZA_V1' AND idempotency_key=%s""", (f"{TAG}-{key}",))
    if done:
        print(f"\n--- rettifica {key}: gia' eseguita, salto.")
        return
    args = ["movimento", "rettifica-giacenza", "--varieta", varieta, "--unita-misura", "SET",
            "--quantita", qty, "--effective-at", when, "--motivo", motivo, "--actor", ACTOR,
            "--reason", motivo, "--correlation-id", f"{TAG}-{key}", "--idempotency-key", f"{TAG}-{key}",
            "--confirm"]
    if semina:
        args[args.index("--effective-at"):args.index("--effective-at")] = ["--semina", semina]
    ctx.tpo(args, f"rettifica giacenza {varieta} -{qty} SET")


# --- fasi --------------------------------------------------------------------
def fase1(ctx: Ctx) -> None:
    ctx.check_head()
    for nome, qty, chiave in PULIZIA:
        key = f"pulizia-{chiave}"
        done = ctx.one("""SELECT 1 FROM tpo.movimento_carico_requests
                          WHERE operation_scope='MOVIMENTO_RETTIFICA_GIACENZA_V1' AND idempotency_key=%s""",
                       (f"{TAG}-{key}",))
        stock = ctx.one("""SELECT s.disponibile FROM tpo.stock s JOIN tpo.varieta v ON v.id=s.varieta_id
                           WHERE v.public_id=%s AND s.unita_misura='SET'""", (VAR[nome],))
        print(f"\n[{nome}] stock SET nel sistema: {stock and stock[0]}")
        if not done and (stock is None or str(stock[0]) != f"{float(qty):.6f}"):
            raise Stop(f"{nome}: lo stock atteso era {qty} SET, nel sistema c'e' {stock and stock[0]}. "
                       "Non rettifico alla cieca: dimmi cosa e' cambiato.")
        rettifica(ctx, VAR[nome], qty, "2026-10-03T08:00:00+01:00",
                  f"Vendita non registrata (storico, lotti non ricostruibili): {nome} {qty} SET fisicamente non piu' presente",
                  key)


def fase2(ctx: Ctx) -> None:
    ctx.check_head()
    for semina, steps in LIFECYCLE.items():
        row = ctx.one("SELECT stato::text, version, data_avvio FROM tpo.semine WHERE public_id=%s", (semina,))
        if row is None:
            raise Stop(f"{semina} inesistente")
        stato, version, avvio = row
        last = ctx.one("SELECT max(effective_at) FROM tpo.semina_lifecycle_eventi e "
                       "JOIN tpo.semine s ON s.id=e.semina_id WHERE s.public_id=%s", (semina,))
        prev = last[0] if last and last[0] else avvio
        print(f"\n[{semina}] stato {stato}, versione {version}, avvio {avvio:%Y-%m-%d %H:%M}")
        for target, when in steps:
            if CHAIN.index(stato) >= CHAIN.index(target):
                continue
            if CHAIN.index(target) != CHAIN.index(stato) + 1:
                raise Stop(f"{semina}: da {stato} a {target} serve passare per uno stato intermedio non pianificato")
            if when.startswith("avvio+"):
                eff = avvio + timedelta(days=int(when.split("+")[1]))
            else:
                eff = datetime.fromisoformat(when)
            if eff < prev:
                raise Stop(f"{semina}: {target} effettiva {eff:%Y-%m-%d %H:%M} precede l'evento precedente {prev:%Y-%m-%d %H:%M}")
            reason = (f"Transizione amministrativa {target} (data di comodo, non osservazione reale): "
                      f"stato fisico riportato da Matteo il 3/10/2026")
            ctx.tpo(["semina", "transition", "--semina", semina, "--expected-semina-version", str(version),
                     "--target-state", target, "--effective-at", eff.isoformat(), "--provenance", PROV,
                     "--actor", ACTOR, "--reason", reason,
                     "--correlation-id", f"{TAG}-lifecycle-{semina}-{target}",
                     "--idempotency-key", f"{TAG}-lifecycle-{semina}-{target}", "--confirm"],
                    f"{semina} -> {target} ({eff:%Y-%m-%d %H:%M})")
            stato, version, prev = target, version + 1, eff


def fase3(ctx: Ctx) -> None:
    ctx.check_head()
    for semina, qty, when, nome in RACCOLTE:
        stato = ctx.one("SELECT stato::text FROM tpo.semine WHERE public_id=%s", (semina,))
        if stato is None or stato[0] != "PRONTA_ALLA_RACCOLTA":
            raise Stop(f"{semina} ({nome}) e' {stato and stato[0]}: lancia prima la fase 2.")
        note = f"Raccolta {nome} {qty} SET ({semina}) dichiarata da Matteo il 3/10/2026"
        out = ctx.tpo(["raccolta", "record", "--semina", semina, "--quantity", qty, "--uom", "SET",
                       "--effective-at", when, "--notes", note, "--actor", ACTOR, "--reason", note,
                       "--correlation-id", f"{TAG}-raccolta-{semina}",
                       "--idempotency-key", f"{TAG}-raccolta-{semina}", "--confirm"],
                      f"raccolta {nome} {qty} SET")
        rac = kv(out, "RACCOLTA_ID") or "RAC-??????(da anteprima)"
        motivo = f"Carico magazzino da raccolta {nome} {qty} SET ({semina})"
        ctx.tpo(["movimento", "carica-raccolta", "--raccolta", rac, "--unita-misura", "SET",
                 "--effective-at", when, "--motivo", motivo, "--actor", ACTOR, "--reason", motivo,
                 "--correlation-id", f"{TAG}-carico-{semina}",
                 "--idempotency-key", f"{TAG}-carico-{semina}", "--confirm"],
                f"carico {rac} ({nome})")


def fase4(ctx: Ctx) -> None:
    ctx.check_head()
    for nome, qty, semina, when, perche in RETTIFICHE_VENDUTO:
        rettifica(ctx, VAR[nome], qty, when,
                  f"Vendita non registrata: {nome} {qty} SET, {perche}",
                  f"venduto-{nome.lower()}-{semina}", semina)


def _crea_ordine(ctx: Ctx, cli: str, righe: list[tuple[str, str]], data_consegna: str, key: str,
                 reason: str) -> dict:
    args = ["ordine", "registra-manuale", "--client", cli, "--data-ordine", "2026-10-03",
            "--data-consegna-prevista", data_consegna]
    for var, qty in righe:
        args += ["--riga", f"{var}:{qty}:SET"]
    args += ["--actor", ACTOR, "--reason", reason, "--correlation-id", f"{TAG}-{key}",
             "--idempotency-key", f"{TAG}-{key}", "--confirm"]
    out = ctx.tpo(args, f"ordine manuale {key}")
    if not ctx.execute:
        return {}
    ordine = kv(out, "ORDINE_ID")
    righe_out = {m.group(2): (m.group(1), m.group(0)) for m in
                 re.finditer(r"RIGA=(RO-\d+) POS=\d+ VARIETA=(VAR-\d+)", out)}
    if not ordine or not righe_out:
        raise Stop("output dell'ordine manuale non riconosciuto")
    return {"ordine": ordine, "righe": {v: r[0] for v, r in righe_out.items()}}


def _ordine_da_key(ctx: Ctx, key: str) -> dict | None:
    row = ctx.one("""SELECT o.public_id FROM tpo.ordine_manuale_requests q JOIN tpo.ordini o ON o.id=q.ordine_id
                     WHERE q.idempotency_key=%s AND q.outcome='COMMITTED'""", (f"{TAG}-{key}",))
    if not row:
        return None
    righe = ctx.q("""SELECT v.public_id, ro.public_id FROM tpo.righe_ordine ro JOIN tpo.ordini o ON o.id=ro.ordine_id
                     JOIN tpo.varieta v ON v.id=ro.varieta_id WHERE o.public_id=%s""", (row[0],))
    return {"ordine": row[0], "righe": {v: r for v, r in righe}}


def _versioni(ctx: Ctx, ordine: str, riga: str) -> tuple[int, int]:
    o = ctx.one("SELECT version FROM tpo.ordini WHERE public_id=%s", (ordine,))
    r = ctx.one("SELECT version FROM tpo.righe_ordine WHERE public_id=%s", (riga,))
    if o is None or r is None:
        raise Stop(f"{ordine}/{riga} inesistente")
    return int(o[0]), int(r[0])


def _consegna(ctx: Ctx, cli: str, planned: str, effective: str, righe: list[dict], tag: str,
              reason: str) -> str | None:
    path = WORK / f"consegna_{tag}.json"
    WORK.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(righe, indent=2))
    out = ctx.tpo(["delivery", "fulfil", "--client", cli, "--planned-date", planned,
                   "--effective-at", effective, "--lines-file", str(path), "--actor", ACTOR,
                   "--reason", reason, "--correlation-id", f"{TAG}-consegna-{tag}", "--confirm"],
                  f"consegna {tag}")
    return kv(out, "CONSEGNA_ID")


def _bolla(ctx: Ctx, consegna: str | None) -> None:
    if consegna is None:
        print("\n--- bolla: in anteprima non c'e' ancora un numero di consegna.")
        return
    ctx.pdf_dir.mkdir(parents=True, exist_ok=True)
    ctx.tpo(["bolla", "genera", "--consegna", consegna, "--output-dir", str(ctx.pdf_dir)],
            f"bolla PDF {consegna}")


def fase5(ctx: Ctx) -> None:
    ctx.check_head()
    cli = cliente_id(ctx, GUSTAVO)
    if cli:
        print(f"\n[{GUSTAVO}] cliente gia' esistente: {cli}")
    else:
        nxt = ctx.one("SELECT COALESCE(max(substring(public_id from 5)::int),0)+1 FROM tpo.clienti")[0]
        cli = f"CLI-{int(nxt):06d}"
        ctx.tpo(["onboarding", "customer", "--customer-id", cli, "--denomination", GUSTAVO,
                 "--actor", ACTOR, "--reason", "Cliente occasionale (vendita extra del 3/10/2026), dati fiscali non ancora disponibili",
                 "--correlation-id", f"{TAG}-cliente-gustavo"], f"nuovo cliente {GUSTAVO} ({cli})")
    key = "ordine-gustavo"
    ordine = _ordine_da_key(ctx, key) or _crea_ordine(
        ctx, cli, [(VAR[n], q) for n, q, _ in GUSTAVO_RIGHE], "2026-10-03", key,
        "Vendita extra del 3/10/2026 a Gustavo La Mamma (possibile futuro cliente, manifestazione nazionale)")
    if not ordine:
        print("\n(anteprima: le righe dell'ordine non esistono ancora; la consegna verra' costruita dopo)")
        return
    stato = ctx.one("SELECT stato::text FROM tpo.ordini WHERE public_id=%s", (ordine["ordine"],))[0]
    if stato == "EVASO":
        print(f"\n{ordine['ordine']} gia' EVASO: consegna gia' registrata, salto.")
        return
    righe = []
    for nome, qty, semina in GUSTAVO_RIGHE:
        riga = ordine["righe"][VAR[nome]]
        ov, rv = _versioni(ctx, ordine["ordine"], riga)
        righe.append({"order_id": ordine["ordine"], "order_line_id": riga, "quantity": qty, "unit": "SET",
                      "expected_order_version": ov, "expected_order_line_version": rv, "semina": semina})
    con = _consegna(ctx, cli, "2026-10-03", "2026-10-03T09:00:00+01:00", righe, "gustavo",
                    "Consegna extra del 3/10/2026 a Gustavo La Mamma")
    _bolla(ctx, con)


def fase6(ctx: Ctx) -> None:
    ctx.check_head()
    cli = cliente_id(ctx, BAHIA_CLIENTE_NOME)
    if not cli:
        raise Stop("cliente Bahia non trovato")
    key = "ordine-bahia-mizuna-hinojo"
    if _ordine_da_key(ctx, key):
        print("\nOrdine manuale Bahia (Mizuna + Hinojo) gia' registrato, salto.")
        return
    _crea_ordine(ctx, cli, [(VAR[n], q) for n, q, _ in BAHIA_NUOVE], BAHIA_PREVISTA, key,
                 "Righe aggiuntive per la prima consegna a Bahia Real (lunedi' 5/10/2026): Mizuna 1 + Hinojo 1")


def fase7(ctx: Ctx, effective: str | None) -> None:
    ctx.check_head()
    cli = cliente_id(ctx, BAHIA_CLIENTE_NOME)
    nuovo = _ordine_da_key(ctx, "ordine-bahia-mizuna-hinojo")
    if not cli or not nuovo:
        raise Stop("manca l'ordine Bahia: lancia prima la fase 6 (con --esegui).")
    ord46, ro_afila = BAHIA_ORDINE_RIGA_AFILA
    gia = ctx.one("""SELECT COALESCE(sum(rc.quantita),0) FROM tpo.righe_consegna rc JOIN tpo.righe_ordine ro ON ro.id=rc.riga_ordine_id
                     JOIN tpo.consegne c ON c.id=rc.consegna_id WHERE ro.public_id=%s AND c.stato='CONSEGNATA'""", (ro_afila,))[0]
    if gia and gia > 0:
        print(f"\n{ro_afila} gia' consegnata ({gia}): consegna Bahia gia' registrata, salto.")
        return
    righe = []
    ov, rv = _versioni(ctx, ord46, ro_afila)
    righe.append({"order_id": ord46, "order_line_id": ro_afila, "quantity": "1", "unit": "SET",
                  "expected_order_version": ov, "expected_order_line_version": rv, "semina": "SEM-000002"})
    for nome, qty, semina in BAHIA_NUOVE:
        riga = nuovo["righe"][VAR[nome]]
        ov, rv = _versioni(ctx, nuovo["ordine"], riga)
        righe.append({"order_id": nuovo["ordine"], "order_line_id": riga, "quantity": qty, "unit": "SET",
                      "expected_order_version": ov, "expected_order_line_version": rv, "semina": semina})
    when = effective or datetime.now().astimezone().replace(microsecond=0).isoformat()
    con = _consegna(ctx, cli, BAHIA_PREVISTA, when, righe, "bahia",
                    "Prima consegna a Hotel Secret Bahia Real (lunedi' 5/10/2026, anticipata di un giorno)")
    _bolla(ctx, con)


def fase8(ctx: Ctx, esito: str | None) -> None:
    ctx.check_head()
    if esito is None:
        raise Stop("fase 8: indica l'esito con --esito \"raccolta completa\" | \"raccolta parziale con scarto\" | "
                   "\"scarto totale\" | \"interruzione\" (scelta tua: nessuna raccolta risulta registrata per SEM-000006).")
    row = ctx.one("SELECT stato::text, version FROM tpo.semine WHERE public_id='SEM-000006'")
    if row[0] == "CHIUSA":
        print("\nSEM-000006 gia' chiusa, salto.")
        return
    reason = ("Rabano 17/9 venduto, non esiste piu': vendita non registrata. Esito dichiarato da Matteo il 3/10/2026; "
              "nessuna RACCOLTA registrata per questa semina")
    ctx.tpo(["semina", "transition", "--semina", "SEM-000006", "--expected-semina-version", str(row[1]),
             "--target-state", "CHIUSA", "--effective-at", "2026-10-03T08:00:00+01:00",
             "--final-outcome", esito,
             "--provenance", '{"target_state":"OWNER_AUTHORIZED","effective_at":"OWNER_AUTHORIZED","final_outcome":"OWNER_AUTHORIZED"}',
             "--actor", ACTOR, "--reason", reason, "--correlation-id", f"{TAG}-chiudi-SEM-000006",
             "--idempotency-key", f"{TAG}-chiudi-SEM-000006", "--confirm"], "chiusura SEM-000006")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fase", required=True, type=int, choices=range(1, 9))
    p.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    p.add_argument("--pdf-dir", default=str(PDF_DIR_DEFAULT), help="cartella dei PDF (default: Scrivania/bolle)")
    p.add_argument("--effective-at", help="solo fase 7: istante della consegna (default: adesso)")
    p.add_argument("--esito", choices=["raccolta completa", "raccolta parziale con scarto", "scarto totale", "interruzione"],
                   help="solo fase 8: esito finale con cui chiudere SEM-000006")
    args = p.parse_args()
    ctx = Ctx(args.esegui, Path(args.pdf_dir))
    try:
        print(f"== FASE {args.fase} -- {'ESECUZIONE' if args.esegui else 'ANTEPRIMA (nulla viene scritto)'}")
        {1: fase1, 2: fase2, 3: fase3, 4: fase4, 5: fase5, 6: fase6,
         7: lambda c: fase7(c, args.effective_at), 8: lambda c: fase8(c, args.esito)}[args.fase](ctx)
        print("\n== FINE FASE", args.fase)
        return 0
    except Stop as exc:
        print(f"\nSTOP: {exc}", file=sys.stderr)
        return 1
    finally:
        ctx.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
