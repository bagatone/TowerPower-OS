"""Consegne di lunedi' 5/10/2026 con bolla PDF (albaran con i codici di tracciabilita').

  --parte bahia    Hotel Secret Bahia Real: Afila 1 SET + Rabano 1 SET + Mizuna 1 SET
  --parte splash   Splash (cliente nuovo, occasionale, senza dati fiscali): Cilantro 0.5 SET
                   + Albahaca (Basilico) 0.5 SET. L'Albahaca non ha giacenza: serve prima la
                   raccolta di 0.5 SET da una semina di Basilico che indichi tu con
                   --semina-albahaca SEM-... (lo script non sceglie e non inventa nulla).

Regole: nessun dato inventato; nessun cambio di stadio di produzione senza il tuo ok
(se la semina di Albahaca non e' PRONTA_ALLA_RACCOLTA lo script SI FERMA e te lo dice);
senza --esegui NON scrive nulla (anteprima); si ferma al primo errore; rilanciabile
(salta cio' che e' gia' fatto, idempotency-key fisse).

Uso, dalla cartella del progetto:
  .venv/bin/python scripts/commissioning/2026-10-05_consegne_bahia_splash.py --parte bahia            # anteprima
  .venv/bin/python scripts/commissioning/2026-10-05_consegne_bahia_splash.py --parte bahia --esegui   # scrive
  .venv/bin/python scripts/commissioning/2026-10-05_consegne_bahia_splash.py --parte splash --semina-albahaca SEM-...
Le bolle PDF vanno in ~/Desktop/bolle (--pdf-dir per cambiare).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters  # noqa: E402
import psycopg  # noqa: E402

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
ACTOR = "matteo"
TAG = "consegne-2026-10-05"
OGGI = "2026-10-05"
HEAD = "20261003_0037"
WORK = ROOT / "outputs" / "consegne_2026_10_05"
PDF_DIR_DEFAULT = Path.home() / "Desktop" / "bolle"

BAHIA = "Hotel Secret Bahia Real"
BAHIA_RIGHE = [  # (varieta, SET, semina dichiarata per la bolla)
    ("Afila", "1", "SEM-000002"),
    ("Rábano", "1", "SEM-000012"),
    ("Mizuna", "1", "SEM-000004"),
]
SPLASH = "Splash"
SPLASH_CILANTRO = ("Cilantro", "0.5", "SEM-000008")  # RAC-000009 = 0.5 SET da SEM-000008 (fase 3 del 3/10)
SPLASH_ALBAHACA = ("Basilico", "0.5")  # varieta' VAR-000006 (Albahaca/Basil)


class Stop(Exception):
    pass


class Ctx:
    def __init__(self, execute: bool, pdf_dir: Path) -> None:
        self.execute = execute
        self.pdf_dir = pdf_dir
        p = load_postgresql_parameters()
        self.conn = psycopg.connect(
            host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
            sslmode=p["sslmode"], connect_timeout=p["connect_timeout"], autocommit=True)

    def q(self, sql, args=()):
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()

    def one(self, sql, args=()):
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def tpo(self, args, label):
        shown = " ".join(a if re.fullmatch(r"[\w./:+=,@-]+", a) else repr(a) for a in args)
        print(f"\n--- {label}\n$ tpo {shown}")
        if not self.execute:
            print("   (anteprima: non eseguito)")
            return ""
        done = subprocess.run([RUN, *args], capture_output=True, text=True)
        print(((done.stdout or "") + (done.stderr or "")).rstrip())
        if done.returncode != 0:
            raise Stop(f"comando fallito (exit {done.returncode}): {label}")
        return done.stdout

    def check_head(self):
        rev = self.one("SELECT version_num FROM public.alembic_version")
        if not rev or rev[0] != HEAD:
            raise Stop(f"migrazione: alembic e' {rev and rev[0]}, serve {HEAD}.")


def kv(text, key):
    m = re.search(rf"^{re.escape(key)}[=:]\s*(\S+)", text, re.M)
    return m.group(1) if m else None


def varieta_id(ctx, nome):
    row = ctx.one("SELECT public_id FROM tpo.varieta WHERE denominazione=%s", (nome,))
    if not row:
        raise Stop(f"varieta' '{nome}' non trovata")
    return row[0]


def giacenza_set(ctx, var_id):
    row = ctx.one("""SELECT COALESCE(sum(s.disponibile),0) FROM tpo.stock s JOIN tpo.varieta v ON v.id=s.varieta_id
                     WHERE v.public_id=%s AND s.unita_misura='SET'""", (var_id,))
    return Decimal(row[0])


def cliente_id(ctx, nome):
    row = ctx.one("SELECT public_id FROM tpo.clienti WHERE denominazione=%s", (nome,))
    return row[0] if row else None


def versioni(ctx, ordine, riga):
    o = ctx.one("SELECT version FROM tpo.ordini WHERE public_id=%s", (ordine,))
    r = ctx.one("SELECT version FROM tpo.righe_ordine WHERE public_id=%s", (riga,))
    if o is None or r is None:
        raise Stop(f"{ordine}/{riga} inesistente")
    return int(o[0]), int(r[0])


def consegna(ctx, cli, planned, effective, righe, tag, reason):
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / f"consegna_{tag}.json"
    path.write_text(json.dumps(righe, indent=2))
    out = ctx.tpo(["delivery", "fulfil", "--client", cli, "--planned-date", planned, "--effective-at", effective,
                   "--lines-file", str(path), "--actor", ACTOR, "--reason", reason,
                   "--correlation-id", f"{TAG}-consegna-{tag}", "--confirm"], f"consegna {tag}")
    return kv(out, "CONSEGNA_ID")


def bolla(ctx, con):
    if con is None:
        print("\n--- bolla: in anteprima non c'e' ancora un numero di consegna.")
        return
    ctx.pdf_dir.mkdir(parents=True, exist_ok=True)
    ctx.tpo(["bolla", "genera", "--consegna", con, "--output-dir", str(ctx.pdf_dir)], f"bolla PDF {con}")


def righe_aperte(ctx, cli, var_id):
    """Righe d'ordine del cliente per la varieta' con quantita' residua da consegnare (SET)."""
    return ctx.q("""
        SELECT o.public_id, ro.public_id, o.data_consegna_prevista, ro.quantita,
               ro.quantita - COALESCE((SELECT SUM(rc.quantita) FROM tpo.righe_consegna rc
                    JOIN tpo.consegne c ON c.id=rc.consegna_id WHERE rc.riga_ordine_id=ro.id AND c.stato='CONSEGNATA'),0)
        FROM tpo.ordini o JOIN tpo.clienti cl ON cl.id=o.cliente_id
        JOIN tpo.righe_ordine ro ON ro.ordine_id=o.id JOIN tpo.varieta v ON v.id=ro.varieta_id
        WHERE cl.public_id=%s AND v.public_id=%s AND ro.unita_misura='SET'
          AND o.stato IN ('APERTO','PARZIALMENTE_EVASO')
        ORDER BY o.data_consegna_prevista, o.public_id, ro.public_id""", (cli, var_id))


def consegna_gia_fatta(ctx, tag):
    row = ctx.one("""SELECT entity_public_id FROM tpo.audit_eventi
                     WHERE entity_type='CONSEGNA' AND correlation_id=%s ORDER BY id LIMIT 1""",
                  (f"{TAG}-consegna-{tag}",))
    return row[0] if row else None


def parte_bahia(ctx: Ctx, effective: str):
    ctx.check_head()
    fatta = consegna_gia_fatta(ctx, "bahia")
    if fatta:
        print(f"\nConsegna Bahia gia' registrata ({fatta}): non ne creo un'altra. Bolla gia' generata, "
              f"oppure: tpo bolla genera --consegna {fatta} --output-dir ~/Desktop/bolle")
        return
    cli = cliente_id(ctx, BAHIA)
    if not cli:
        raise Stop("cliente Bahia non trovato")
    print(f"\nCliente: {BAHIA} ({cli})")
    righe, planned = [], []
    print("\nRighe d'ordine scelte (la piu' vicina nel tempo con residuo sufficiente) e giacenze:")
    for nome, qty, semina in BAHIA_RIGHE:
        vid = varieta_id(ctx, nome)
        giac = giacenza_set(ctx, vid)
        if giac < Decimal(qty):
            raise Stop(f"{nome}: giacenza {giac} SET < {qty} SET da consegnare.")
        stato = ctx.one("SELECT stato::text FROM tpo.semine WHERE public_id=%s", (semina,))
        if not stato:
            raise Stop(f"semina {semina} inesistente")
        cand = [r for r in righe_aperte(ctx, cli, vid) if Decimal(r[4]) >= Decimal(qty)]
        if not cand:
            raise Stop(f"{nome}: nessuna riga d'ordine Bahia aperta con residuo >= {qty} SET. "
                       "Dimmi come procedere (creare un ordine manuale?).")
        ordine, riga, prevista, ordinato, residuo = cand[0]
        extra = f" [altre righe candidate: {', '.join(f'{c[0]}/{c[1]}' for c in cand[1:])}]" if len(cand) > 1 else ""
        print(f"  {nome}: {qty} SET  <- {ordine} {riga} (prevista {prevista}, ordinato {ordinato}, residuo {residuo}); "
              f"giacenza {giac}; semina dichiarata {semina}{extra}")
        ov, rv = versioni(ctx, ordine, riga)
        righe.append({"order_id": ordine, "order_line_id": riga, "quantity": qty, "unit": "SET",
                      "expected_order_version": ov, "expected_order_line_version": rv, "semina": semina})
        planned.append(prevista)
    con = consegna(ctx, cli, str(min(planned)), effective, righe, "bahia",
                   "Consegna a Hotel Secret Bahia Real del 5/10/2026: Afila 1, Rabano 1, Mizuna 1 SET")
    bolla(ctx, con)


def parte_splash(ctx: Ctx, effective: str, semina_alb: str | None, solo_cilantro: bool = False):
    ctx.check_head()
    sfx = "-cilantro" if solo_cilantro else ""
    fatta = consegna_gia_fatta(ctx, "splash" + sfx)
    if fatta:
        print(f"\nConsegna Splash gia' registrata ({fatta}): non ne creo un'altra. "
              f"Bolla: tpo bolla genera --consegna {fatta} --output-dir ~/Desktop/bolle")
        return
    cli = cliente_id(ctx, SPLASH)
    if cli:
        print(f"\n[{SPLASH}] cliente gia' esistente: {cli}")
    else:
        nxt = ctx.one("SELECT COALESCE(max(substring(public_id from 5)::int),0)+1 FROM tpo.clienti")[0]
        cli = f"CLI-{int(nxt):06d}"
        ctx.tpo(["onboarding", "customer", "--customer-id", cli, "--denomination", SPLASH, "--actor", ACTOR,
                 "--reason", "Cliente occasionale Splash (consegna del 5/10/2026), dati fiscali non ancora disponibili",
                 "--correlation-id", f"{TAG}-cliente-splash"], f"nuovo cliente {SPLASH} ({cli})")
    cil_nome, cil_qty, cil_semina = SPLASH_CILANTRO
    alb_nome, alb_qty = SPLASH_ALBAHACA
    vc, va = varieta_id(ctx, cil_nome), varieta_id(ctx, alb_nome)
    g = giacenza_set(ctx, vc)
    if g < Decimal(cil_qty):
        raise Stop(f"Cilantro: giacenza {g} SET < {cil_qty} SET.")
    rac = ctx.one("""SELECT r.public_id, s.public_id FROM tpo.raccolte r JOIN tpo.semine s ON s.id=r.semina_id
                     WHERE r.public_id='RAC-000009'""")
    if not rac or rac[1] != cil_semina:
        raise Stop(f"RAC-000009 non e' una raccolta di {cil_semina}: dimmi da quale semina viene il Cilantro.")
    print(f"\nCilantro: {cil_qty} SET, giacenza {g}, semina dichiarata {cil_semina} (da {rac[0]})")

    if solo_cilantro:
        print("\nSolo Cilantro: l'Albahaca NON viene consegnata ora (resta da registrare a parte).")
        alb_semina = None
    else:
        # --- Albahaca: giacenza o raccolta da registrare ---
        ga = giacenza_set(ctx, va)
        print(f"\nAlbahaca (Basilico): giacenza {ga} SET, servono {alb_qty} SET")
        if ga < Decimal(alb_qty):
            cand = ctx.q("""SELECT s.public_id, s.codice_tracciabilita, s.stato::text, s.data_avvio::date
                            FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id
                            WHERE v.public_id=%s AND s.stato <> 'CHIUSA' ORDER BY s.data_avvio, s.public_id""", (va,))
            print("Semine di Basilico non chiuse:")
            for c in cand:
                print(f"  {c[0]} {c[1]} {c[2]} (avvio {c[3]})")
            if not semina_alb:
                raise Stop("manca --semina-albahaca SEM-...: indica da quale semina di Basilico viene la raccolta di "
                           f"{alb_qty} SET (scegli dall'elenco qui sopra; non scelgo io).")
            sel = next((c for c in cand if c[0] == semina_alb), None)
            if not sel:
                raise Stop(f"{semina_alb} non e' una semina di Basilico non chiusa.")
            if sel[2] != "PRONTA_ALLA_RACCOLTA":
                raise Stop(f"{semina_alb} e' {sel[2]}, non PRONTA_ALLA_RACCOLTA. Il cambio di stadio e' una tua decisione: "
                           "dimmi esplicitamente se e quando e' pronta e lo porto allo stato fisico (con la data che dichiari).")
            note = f"Raccolta Albahaca {alb_qty} SET ({semina_alb}) dichiarata da Matteo il 5/10/2026"
            out = ctx.tpo(["raccolta", "record", "--semina", semina_alb, "--quantity", alb_qty, "--uom", "SET",
                           "--effective-at", effective, "--notes", note, "--actor", ACTOR, "--reason", note,
                           "--correlation-id", f"{TAG}-raccolta-{semina_alb}",
                           "--idempotency-key", f"{TAG}-raccolta-{semina_alb}", "--confirm"], "raccolta Albahaca")
            racc = kv(out, "RACCOLTA_ID") or "RAC-??????(da anteprima)"
            motivo = f"Carico magazzino da raccolta Albahaca {alb_qty} SET ({semina_alb})"
            ctx.tpo(["movimento", "carica-raccolta", "--raccolta", racc, "--unita-misura", "SET", "--effective-at", effective,
                     "--motivo", motivo, "--actor", ACTOR, "--reason", motivo,
                     "--correlation-id", f"{TAG}-carico-{semina_alb}", "--idempotency-key", f"{TAG}-carico-{semina_alb}",
                     "--confirm"], f"carico {racc} (Albahaca)")
            alb_semina = semina_alb
        else:
            if not semina_alb:
                raise Stop("c'e' giacenza di Albahaca ma non so da quale semina viene: indica --semina-albahaca SEM-...")
            alb_semina = semina_alb

    # --- ordine manuale + consegna ---
    righe_ordine = ["--riga", f"{vc}:{cil_qty}:SET"] + ([] if solo_cilantro else ["--riga", f"{va}:{alb_qty}:SET"])
    motivo_ordine = ("Vendita a Splash del 5/10/2026: Cilantro 0.5 SET (cliente occasionale)" if solo_cilantro else
                     "Vendita a Splash del 5/10/2026: Cilantro 0.5 + Albahaca 0.5 SET (cliente occasionale)")
    key = f"{TAG}-ordine-splash{sfx}"
    row = ctx.one("""SELECT o.public_id FROM tpo.ordine_manuale_requests q JOIN tpo.ordini o ON o.id=q.ordine_id
                     WHERE q.idempotency_key=%s AND q.outcome='COMMITTED'""", (key,))
    if row:
        ordine = row[0]
        righe_o = {v: r for v, r in ctx.q("""SELECT v.public_id, ro.public_id FROM tpo.righe_ordine ro
                   JOIN tpo.ordini o ON o.id=ro.ordine_id JOIN tpo.varieta v ON v.id=ro.varieta_id
                   WHERE o.public_id=%s""", (ordine,))}
        stato = ctx.one("SELECT stato::text FROM tpo.ordini WHERE public_id=%s", (ordine,))[0]
        if stato == "EVASO":
            print(f"\n{ordine} gia' EVASO: consegna Splash gia' registrata, salto.")
            return
    else:
        out = ctx.tpo(["ordine", "registra-manuale", "--client", cli, "--data-ordine", OGGI,
                       "--data-consegna-prevista", OGGI,
                       *righe_ordine, "--actor", ACTOR, "--reason", motivo_ordine,
                       "--correlation-id", key, "--idempotency-key", key, "--confirm"], "ordine manuale Splash")
        if not ctx.execute:
            print("\n(anteprima: l'ordine non esiste ancora; la consegna verra' costruita dopo)")
            return
        ordine = kv(out, "ORDINE_ID")
        righe_o = {m.group(2): m.group(1) for m in re.finditer(r"RIGA=(RO-\d+) POS=\d+ VARIETA=(VAR-\d+)", out)}
        if not ordine or not righe_o:
            raise Stop("output dell'ordine manuale non riconosciuto")
    righe = []
    voci = [(vc, cil_qty, cil_semina)] + ([] if solo_cilantro else [(va, alb_qty, alb_semina)])
    for vid, qty, semina in voci:
        riga = righe_o[vid]
        ov, rv = versioni(ctx, ordine, riga)
        righe.append({"order_id": ordine, "order_line_id": riga, "quantity": qty, "unit": "SET",
                      "expected_order_version": ov, "expected_order_line_version": rv, "semina": semina})
    con = consegna(ctx, cli, OGGI, effective, righe, "splash" + sfx,
                   "Consegna a Splash del 5/10/2026: " + ("Cilantro 0.5 SET" if solo_cilantro else "Cilantro 0.5 + Albahaca 0.5 SET"))
    bolla(ctx, con)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parte", required=True, choices=["bahia", "splash"])
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    ap.add_argument("--effective-at", help="istante della consegna/raccolta ISO 8601 (default: adesso)")
    ap.add_argument("--semina-albahaca", help="semina di Basilico da cui viene la raccolta (solo parte splash)")
    ap.add_argument("--solo-cilantro", action="store_true",
                    help="parte splash: consegna ORA solo il Cilantro (l'Albahaca si registra a parte)")
    ap.add_argument("--pdf-dir", default=str(PDF_DIR_DEFAULT))
    a = ap.parse_args()
    effective = a.effective_at or datetime.now().astimezone().replace(microsecond=0).isoformat()
    ctx = Ctx(a.esegui, Path(a.pdf_dir))
    try:
        print(f"== {a.parte.upper()} -- {'ESECUZIONE' if a.esegui else 'ANTEPRIMA (nulla viene scritto)'} (istante {effective})")
        (parte_bahia(ctx, effective) if a.parte == "bahia" else parte_splash(ctx, effective, a.semina_albahaca, a.solo_cilantro))
        print("\n== FINE")
        return 0
    except Stop as exc:
        print(f"\nSTOP: {exc}", file=sys.stderr)
        return 1
    finally:
        ctx.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
