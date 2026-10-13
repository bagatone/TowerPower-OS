"""Consegne di giovedi' 8/10/2026 (Tagoro e Salvaje) con bolla PDF, in DUE FASI.

Dichiarazioni di Matteo (8/10/2026): Afila 4 SET, Cilantro 4 SET e Rabano 3 SET sono pronti al raccolto.
Consegne di oggi:
  Tagoro  : Cilantro 1 SET (ORD-000018 RO-000038, in ritardo dal 6/10) + Albahaca (Basilico) 0.5 SET
            (Tagoro non ha una riga di Basilico: ordine manuale di oggi, come per Splash)
  Salvaje : Afila 2 SET + Cilantro 0.5 SET + Rabano 0.5 SET (cliente NUOVO e occasionale, senza dati fiscali:
            va registrato; ordine manuale di oggi)

  --fase pronta     porta a PRONTA_ALLA_RACCOLTA SEM-000010 (Afila 4 SET, da CRESCITA) e SEM-000015 (Rabano
                    3 SET, da LUCE passando per CRESCITA, passaggio amministrativo 1 minuto dopo la luce).
                    Cilantro (SEM-000008) e Basilico (SEM-000023) sono gia' PRONTA_ALLA_RACCOLTA.
  --fase consegne   (da lanciare almeno un minuto DOPO la fase pronta) per ogni prodotto registra la raccolta
                    SOLO dei SET che escono oggi + il carico a magazzino, poi cliente/ordini manuali mancanti,
                    le due consegne e le bolle PDF. Il resto resta in campo, non raccolto.

Raccolte di oggi (le semine le hai indicate/confermate tu, lo script non sceglie):
  SEM-000010 Afila 2 | SEM-000008 Cilantro 1.5 | SEM-000023 Basilico 0.5 | SEM-000015 Rabano 0.5

Regole: nessun dato inventato; l'istante delle transizioni e' quello della conferma (non osservato) e viene
scritto nel motivo; senza --esegui NON scrive nulla (anteprima); si ferma al primo errore; rilanciabile (salta
cio' che e' gia' fatto, idempotency-key fisse e istanti salvati in outputs/consegne_2026_10_08).

Uso, dalla cartella del progetto:
  .venv/bin/python scripts/commissioning/2026-10-08_consegne_giornata.py --fase pronta              # anteprima
  .venv/bin/python scripts/commissioning/2026-10-08_consegne_giornata.py --fase pronta --esegui
  .venv/bin/python scripts/commissioning/2026-10-08_consegne_giornata.py --fase consegne            # anteprima
  .venv/bin/python scripts/commissioning/2026-10-08_consegne_giornata.py --fase consegne --esegui
Le bolle PDF vanno in ~/Desktop/bolle (--pdf-dir per cambiare).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

RUN = str(ROOT / "scripts" / "commissioning" / "run_tpo.sh")
ACTOR = "matteo"
TAG = "consegne-2026-10-08"
OGGI = "2026-10-08"
HEAD = "20261003_0037"
WORK = ROOT / "outputs" / "consegne_2026_10_08"
PDF_DIR_DEFAULT = Path.home() / "Desktop" / "bolle"
PROV_TRANS = '{"target_state":"OWNER_AUTHORIZED","effective_at":"OWNER_AUTHORIZED"}'

# (semina, varieta, SET dichiarati pronti da Matteo)
PRONTA = [("SEM-000010", "Afila", "4"), ("SEM-000015", "Rabano", "3")]
# gia' PRONTA_ALLA_RACCOLTA a sistema (verificato prima di scrivere)
GIA_PRONTE = [("SEM-000008", "Cilantro"), ("SEM-000023", "Basilico")]
# (semina, varieta, SET raccolti oggi)
RACCOLTE = [("SEM-000010", "Afila", "2"), ("SEM-000008", "Cilantro", "1.5"),
            ("SEM-000023", "Basilico", "0.5"), ("SEM-000015", "Rabano", "0.5")]
TAGORO = "Tagoro"
TAGORO_CILANTRO = ("ORD-000018", "RO-000038", "Cilantro", "1", "SEM-000008")
TAGORO_MANUALE = [("Basilico", "0.5", "SEM-000023")]
SALVAJE = "Salvaje"
SALVAJE_MANUALE = [("Afila", "2", "SEM-000010"), ("Cilantro", "0.5", "SEM-000008"), ("Rabano", "0.5", "SEM-000015")]
CHAIN = ["AVVIATA", "GERMINAZIONE", "LUCE", "CRESCITA", "PRONTA_ALLA_RACCOLTA"]


class Stop(Exception):
    pass


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn").strip()


def _n(value) -> str:
    return format(Decimal(value).normalize(), "f")


class Ctx:
    def __init__(self, execute: bool, pdf_dir: Path, conn=None) -> None:
        self.execute = execute
        self.pdf_dir = pdf_dir
        if conn is None:
            from secret_boundary import load_postgresql_parameters
            import psycopg
            p = load_postgresql_parameters()
            conn = psycopg.connect(
                host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                sslmode=p["sslmode"], connect_timeout=p["connect_timeout"], autocommit=True)
        self.conn = conn

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


def instant(fase: str, execute: bool, override: str | None) -> datetime:
    """Istante della fase: salvato alla prima esecuzione e riusato nei rilanci (idempotenza)."""
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / "istanti.json"
    saved = json.loads(path.read_text()) if path.exists() else {}
    if override:
        return datetime.fromisoformat(override)
    if fase in saved:
        return datetime.fromisoformat(saved[fase])
    now = datetime.now().astimezone().replace(second=0, microsecond=0)
    if execute:
        saved[fase] = now.isoformat()
        path.write_text(json.dumps(saved, indent=2))
    return now


def semina_row(ctx, semina, varieta):
    row = ctx.one("""SELECT s.stato::text, s.version, s.expected_useful_quantity, s.expected_useful_uom::text,
                            v.denominazione, s.codice_tracciabilita,
                            COALESCE((SELECT SUM(r.quantita) FROM tpo.raccolte r
                                      WHERE r.semina_id=s.id AND r.unita_misura='SET'),0)
                     FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id WHERE s.public_id=%s""", (semina,))
    if not row:
        raise Stop(f"semina {semina} inesistente")
    if _fold(row[4]) != _fold(varieta):
        raise Stop(f"{semina} e' {row[4]}, non {varieta}.")
    return row


def ultimo_evento(ctx, semina):
    row = ctx.one("""SELECT max(e.effective_at) FROM tpo.semina_lifecycle_eventi e
                     JOIN tpo.semine s ON s.id=e.semina_id WHERE s.public_id=%s""", (semina,))
    return row[0] if row else None


def fase_pronta(ctx: Ctx, t: datetime):
    ctx.check_head()
    print(f"\nPassaggio a PRONTA_ALLA_RACCOLTA all'istante {t:%Y-%m-%d %H:%M} (conferma; orario fisico non osservato)")
    for semina, varieta, dichiarati in PRONTA:
        stato, version, attesi, uom, _, codice, raccolti = semina_row(ctx, semina, varieta)
        print(f"\n{semina} {codice} {varieta}: {stato}, attesi {_n(attesi) if attesi is not None else '?'} {uom or ''}, "
              f"dichiarati pronti da Matteo {dichiarati} SET")
        if attesi is None or uom != "SET" or Decimal(attesi) != Decimal(dichiarati):
            raise Stop(f"{semina}: i SET attesi a sistema non coincidono con i {dichiarati} SET dichiarati. "
                       "Non scelgo io: dimmi quale semina e' pronta.")
        if stato == "PRONTA_ALLA_RACCOLTA":
            print("  gia' PRONTA_ALLA_RACCOLTA: nulla da fare")
            continue
        if stato not in ("LUCE", "CRESCITA"):
            raise Stop(f"{semina} e' {stato}: la fase pronta parte da LUCE o CRESCITA.")
        ultimo = ultimo_evento(ctx, semina)
        steps = []
        if stato == "LUCE":
            if ultimo is None:
                raise Stop(f"{semina}: nessun evento di ciclo di vita, non posso datare CRESCITA.")
            steps.append(("CRESCITA", ultimo + timedelta(minutes=1),
                          "passaggio amministrativo 1 minuto dopo la luce (LUCE e CRESCITA sono lo stesso processo)"))
        steps.append(("PRONTA_ALLA_RACCOLTA", t,
                      f"dichiarata da Matteo l'8/10/2026 ({varieta} {dichiarati} SET pronti al raccolto); "
                      "orario non osservato, registrato alla conferma"))
        previous = ultimo
        for nome, when, nota in steps:
            if previous is not None and when <= previous:
                raise Stop(f"{semina}: {nome} {when:%Y-%m-%d %H:%M} non e' dopo l'ultimo evento {previous:%Y-%m-%d %H:%M}.")
            previous = when
        for nome, when, nota in steps:
            reason = f"Transizione {nome} {semina} del {when:%d/%m/%Y %H:%M}: {nota}"
            ctx.tpo(["semina", "transition", "--semina", semina, "--expected-semina-version", str(version),
                     "--target-state", nome, "--effective-at", when.isoformat(), "--provenance", PROV_TRANS,
                     "--actor", ACTOR, "--reason", reason,
                     "--correlation-id", f"{TAG}-lifecycle-{semina}-{nome}",
                     "--idempotency-key", f"{TAG}-lifecycle-{semina}-{nome}", "--confirm"], f"{semina} -> {nome}")
            version += 1
    print("\nGia' pronte a sistema (verifica):")
    for semina, varieta in GIA_PRONTE:
        stato, *_ = semina_row(ctx, semina, varieta)
        if stato != "PRONTA_ALLA_RACCOLTA":
            raise Stop(f"{semina} e' {stato}, non PRONTA_ALLA_RACCOLTA: dimmi come procedere.")
        print(f"  {semina} {varieta}: {stato}")


def varieta_id(ctx, nome):
    for pid, name in ctx.q("SELECT public_id, denominazione FROM tpo.varieta"):
        if _fold(name) == _fold(nome):
            return pid
    raise Stop(f"varieta' '{nome}' non trovata")


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


def audit_fatto(ctx, entity, correlation):
    row = ctx.one("""SELECT entity_public_id FROM tpo.audit_eventi
                     WHERE entity_type=%s AND correlation_id=%s ORDER BY id LIMIT 1""", (entity, correlation))
    return row[0] if row else None


def raccolte(ctx: Ctx, t: datetime):
    print("\n== RACCOLTE E CARICHI A MAGAZZINO (solo i SET che escono oggi)")
    ids = {}
    for semina, varieta, qty in RACCOLTE:
        stato, _, attesi, uom, _, codice, raccolti = semina_row(ctx, semina, varieta)
        if stato != "PRONTA_ALLA_RACCOLTA":
            raise Stop(f"{semina} e' {stato}, non PRONTA_ALLA_RACCOLTA: lancia prima la fase pronta.")
        ultimo = ultimo_evento(ctx, semina)
        if ultimo is not None and t <= ultimo:
            raise Stop(f"{semina}: la raccolta ({t:%H:%M}) non e' dopo l'ultimo evento ({ultimo:%Y-%m-%d %H:%M}). "
                       "Aspetta un minuto e rilancia.")
        done = audit_fatto(ctx, "RACCOLTA", f"{TAG}-raccolta-{semina}")
        vid = varieta_id(ctx, varieta)
        giac = giacenza_set(ctx, vid)
        if not done and giac != 0:
            raise Stop(f"{varieta}: giacenza {_n(giac)} SET diversa da 0 prima del carico: dimmi come procedere.")
        if not done and attesi is not None and Decimal(raccolti) + Decimal(qty) > Decimal(attesi):
            raise Stop(f"{semina}: {_n(raccolti)} gia' raccolti + {qty} superano gli attesi {_n(attesi)} SET.")
        print(f"\n{varieta}: {qty} SET da {semina} ({codice}); giacenza {_n(giac)}; gia' raccolti {_n(raccolti)} "
              f"su {_n(attesi) if attesi is not None else '?'}" + ("  [raccolta gia' registrata]" if done else ""))
        note = f"Raccolta {varieta} {qty} SET ({semina}) dichiarata da Matteo l'8/10/2026"
        out = ctx.tpo(["raccolta", "record", "--semina", semina, "--quantity", qty, "--uom", "SET",
                       "--effective-at", t.isoformat(), "--notes", note, "--actor", ACTOR, "--reason", note,
                       "--correlation-id", f"{TAG}-raccolta-{semina}",
                       "--idempotency-key", f"{TAG}-raccolta-{semina}", "--confirm"], f"raccolta {varieta}")
        racc = kv(out, "RACCOLTA_ID") or "RAC-??????(da anteprima)"
        motivo = f"Carico magazzino da raccolta {varieta} {qty} SET ({semina})"
        ctx.tpo(["movimento", "carica-raccolta", "--raccolta", racc, "--unita-misura", "SET", "--effective-at",
                 t.isoformat(), "--motivo", motivo, "--actor", ACTOR, "--reason", motivo,
                 "--correlation-id", f"{TAG}-carico-{semina}", "--idempotency-key", f"{TAG}-carico-{semina}",
                 "--confirm"], f"carico {racc} ({varieta})")
        ids[semina] = racc
    return ids


def righe_aperte(ctx, cli, var_id):
    return ctx.q("""
        SELECT o.public_id, ro.public_id, o.data_consegna_prevista, ro.quantita,
               ro.quantita - COALESCE((SELECT SUM(rc.quantita) FROM tpo.righe_consegna rc
                    JOIN tpo.consegne c ON c.id=rc.consegna_id WHERE rc.riga_ordine_id=ro.id AND c.stato='CONSEGNATA'),0)
        FROM tpo.ordini o JOIN tpo.righe_ordine ro ON ro.ordine_id=o.id JOIN tpo.varieta v ON v.id=ro.varieta_id
        JOIN tpo.clienti cl ON cl.id=o.cliente_id
        WHERE cl.public_id=%s AND v.public_id=%s AND ro.unita_misura='SET'
          AND o.stato IN ('APERTO','PARZIALMENTE_EVASO')
        ORDER BY o.data_consegna_prevista, o.public_id, ro.public_id""", (cli, var_id))


def ordine_manuale(ctx: Ctx, cli, voci, tag, motivo):
    """Crea (o ritrova) l'ordine manuale di oggi; ritorna (ordine, {varieta_id: riga}) oppure (None, None) in anteprima."""
    key = f"{TAG}-ordine-{tag}"
    row = ctx.one("""SELECT o.public_id FROM tpo.ordine_manuale_requests q JOIN tpo.ordini o ON o.id=q.ordine_id
                     WHERE q.idempotency_key=%s AND q.outcome='COMMITTED'""", (key,))
    if row:
        ordine = row[0]
        righe = {v: r for v, r in ctx.q("""SELECT v.public_id, ro.public_id FROM tpo.righe_ordine ro
                   JOIN tpo.ordini o ON o.id=ro.ordine_id JOIN tpo.varieta v ON v.id=ro.varieta_id
                   WHERE o.public_id=%s""", (ordine,))}
        print(f"\nOrdine manuale {tag} gia' registrato: {ordine}")
        return ordine, righe
    righe_cli = []
    for nome, qty, _ in voci:
        righe_cli += ["--riga", f"{varieta_id(ctx, nome)}:{qty}:SET"]
    out = ctx.tpo(["ordine", "registra-manuale", "--client", cli, "--data-ordine", OGGI,
                   "--data-consegna-prevista", OGGI, *righe_cli, "--actor", ACTOR, "--reason", motivo,
                   "--correlation-id", key, "--idempotency-key", key, "--confirm"], f"ordine manuale {tag}")
    if not ctx.execute:
        return None, None
    ordine = kv(out, "ORDINE_ID")
    righe = {m.group(2): m.group(1) for m in re.finditer(r"RIGA=(RO-\d+) POS=\d+ VARIETA=(VAR-\d+)", out)}
    if not ordine or not righe:
        raise Stop("output dell'ordine manuale non riconosciuto")
    return ordine, righe


def consegna(ctx: Ctx, cli, planned, effective, righe, tag, reason):
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
    ctx.tpo(["bolla", "genera", "--consegna", con, "--output-dir", str(ctx.pdf_dir), "--per-cliente"],
            f"bolla PDF {con}")


def righe_consegna(ctx, ordine, righe_o, voci):
    out = []
    for nome, qty, semina in voci:
        riga = righe_o[varieta_id(ctx, nome)]
        ov, rv = versioni(ctx, ordine, riga)
        out.append({"order_id": ordine, "order_line_id": riga, "quantity": qty, "unit": "SET",
                    "expected_order_version": ov, "expected_order_line_version": rv, "semina": semina})
    return out


def fase_consegne(ctx: Ctx, t: datetime):
    ctx.check_head()
    ordine_id, riga_id, nome, qty, semina = TAGORO_CILANTRO
    tagoro = cliente_id(ctx, TAGORO)
    if not tagoro:
        raise Stop("cliente Tagoro non trovato")
    vc = varieta_id(ctx, nome)
    cand = [r for r in righe_aperte(ctx, tagoro, vc) if r[0] == ordine_id and r[1] == riga_id]
    fatta_tagoro = audit_fatto(ctx, "CONSEGNA", f"{TAG}-consegna-tagoro")
    fatta_salvaje = audit_fatto(ctx, "CONSEGNA", f"{TAG}-consegna-salvaje")
    if not cand and not fatta_tagoro:
        raise Stop(f"{ordine_id}/{riga_id} non e' piu' una riga aperta di Tagoro con residuo.")
    if cand and Decimal(cand[0][4]) < Decimal(qty):
        raise Stop(f"{ordine_id}/{riga_id}: residuo {cand[0][4]} < {qty} SET.")
    raccolte(ctx, t)

    print("\n== CLIENTE SALVAJE (nuovo, occasionale, senza dati fiscali)")
    salvaje = cliente_id(ctx, SALVAJE)
    if salvaje:
        print(f"  gia' esistente: {salvaje}")
    else:
        nxt = ctx.one("SELECT COALESCE(max(substring(public_id from 5)::int),0)+1 FROM tpo.clienti")[0]
        salvaje = f"CLI-{int(nxt):06d}"
        ctx.tpo(["onboarding", "customer", "--customer-id", salvaje, "--denomination", SALVAJE, "--actor", ACTOR,
                 "--reason", "Cliente occasionale Salvaje (consegna dell'8/10/2026), dati fiscali non ancora disponibili",
                 "--correlation-id", f"{TAG}-cliente-salvaje"], f"nuovo cliente {SALVAJE} ({salvaje})")

    print("\n== TAGORO")
    if fatta_tagoro:
        print(f"  consegna gia' registrata ({fatta_tagoro}): salto.")
    else:
        ord_man, righe_man = ordine_manuale(
            ctx, tagoro, TAGORO_MANUALE, "tagoro",
            "Vendita a Tagoro dell'8/10/2026: Albahaca (Basilico) 0.5 SET, fuori dal programma settimanale")
        if ord_man is None:
            print("  (anteprima) consegna: Cilantro 1 SET su ORD-000018 RO-000038 (semina SEM-000008) "
                  "+ Basilico 0.5 SET su nuovo ordine manuale (semina SEM-000023)")
        else:
            ov, rv = versioni(ctx, ordine_id, riga_id)
            righe = [{"order_id": ordine_id, "order_line_id": riga_id, "quantity": qty, "unit": "SET",
                      "expected_order_version": ov, "expected_order_line_version": rv, "semina": semina}]
            righe += righe_consegna(ctx, ord_man, righe_man, TAGORO_MANUALE)
            con = consegna(ctx, tagoro, min("2026-10-06", OGGI), t.isoformat(), righe, "tagoro",
                           "Consegna a Tagoro dell'8/10/2026: Cilantro 1 + Albahaca 0.5 SET")
            bolla(ctx, con)

    print("\n== SALVAJE")
    if fatta_salvaje:
        print(f"  consegna gia' registrata ({fatta_salvaje}): salto.")
    else:
        ord_man, righe_man = ordine_manuale(
            ctx, salvaje, SALVAJE_MANUALE, "salvaje",
            "Vendita a Salvaje dell'8/10/2026: Afila 2 + Cilantro 0.5 + Rabano 0.5 SET (cliente occasionale)")
        if ord_man is None:
            print("  (anteprima) consegna: Afila 2 (SEM-000010) + Cilantro 0.5 (SEM-000008) + Rabano 0.5 (SEM-000015) "
                  "su nuovo ordine manuale")
        else:
            con = consegna(ctx, salvaje, OGGI, t.isoformat(), righe_consegna(ctx, ord_man, righe_man, SALVAJE_MANUALE),
                           "salvaje", "Consegna a Salvaje dell'8/10/2026: Afila 2, Cilantro 0.5, Rabano 0.5 SET")
            bolla(ctx, con)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fase", required=True, choices=["pronta", "consegne"])
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    ap.add_argument("--effective-at", help="istante ISO 8601 della fase (default: adesso, salvato al primo --esegui)")
    ap.add_argument("--pdf-dir", default=str(PDF_DIR_DEFAULT))
    a = ap.parse_args()
    t = instant(a.fase, a.esegui, a.effective_at)
    ctx = Ctx(a.esegui, Path(a.pdf_dir))
    try:
        print(f"== FASE {a.fase.upper()} -- {'ESECUZIONE' if a.esegui else 'ANTEPRIMA (nulla viene scritto)'} "
              f"(istante {t.isoformat()})")
        (fase_pronta if a.fase == "pronta" else fase_consegne)(ctx, t)
        print("\n== FINE")
        return 0
    except Stop as exc:
        print(f"\nSTOP: {exc}", file=sys.stderr)
        return 1
    finally:
        ctx.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
