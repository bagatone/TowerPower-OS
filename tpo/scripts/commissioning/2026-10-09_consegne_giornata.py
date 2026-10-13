"""Consegne di venerdi' 9/10/2026: Splash, Azul y Sal, El Callao, Alchimia Sushi, con bolla PDF.

Dichiarazioni di Matteo (9/10/2026) e situazione verificata a sistema (stato_consegne.py delle 10:14):
  Splash     : ORD-000044 (Cilantro 1 + Basilico 1, prevista 6/10). La prima meta' (Cilantro 0.5 + Basilico 0.5) e'
               gia' stata consegnata con CON-000005 (5/10), registrata senza legarla all'ordine. Quindi oggi 0.5 + 0.5:
               lo script porta PRIMA le due righe a 0.5 (modifica ordine con audit, originale conservato) e poi consegna.
  Azul y Sal : ORD-000042 RO-000100 (Cilantro 3, venerdi' 9/10): oggi Cilantro 2 (--azul-cilantro per cambiare).
               Il residuo resta aperto come dovuto.
  El Callao  : Afila 1 SET, cliente trattato come occasionale: ordine manuale di oggi. L'ordine del programma
               ORD-000039 (16/10, Afila 2) NON viene toccato.
  Alchimia   : ORD-000040 (9/10): Afila 0.5 + Rabano 0.5 + Hinojo 0.5 (1.5 SET). La riga Mizuna 0.5 resta aperta.
               Il Pak Choi di prova (mai registrato) resta FUORI dal sistema, per scelta di Matteo.

Raccolte di oggi (solo i SET venduti oggi; le semine le hai indicate tu, lo script non sceglie):
  SEM-000008 Cilantro 0.5 + Azul | SEM-000010 Afila 1.5 | SEM-000023 Basilico 0.5 | SEM-000015 Rabano 0.5
  L'Hinojo 0.5 esce dalla giacenza (1.5 SET, SEM-000005): nessuna raccolta.
Le semine sono gia' tutte PRONTA_ALLA_RACCOLTA (nessuna fase 'pronta').

Regole: nessun dato inventato; senza --esegui NON scrive nulla (anteprima, compresa la modifica ordine); si ferma al
primo errore; rilanciabile (salta cio' che e' gia' fatto: idempotency-key fisse, istante salvato in
outputs/consegne_2026_10_09). Una raccolta oltre i SET attesi dal sistema si ferma, a meno di --oltre-attesi
(dichiarazione tua: gli attesi sono una stima).

Uso, dalla cartella del progetto:
  .venv/bin/python scripts/commissioning/2026-10-09_consegne_giornata.py                  # anteprima
  .venv/bin/python scripts/commissioning/2026-10-09_consegne_giornata.py --esegui
Opzioni: --azul-cilantro 1.5   --oltre-attesi   --pdf-dir CARTELLA (default ~/Desktop/bolle)
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

BASE_SCRIPT = ROOT / "scripts" / "commissioning" / "2026-10-08_consegne_giornata.py"
TAG = "consegne-2026-10-09"
OGGI = "2026-10-09"
WORK = ROOT / "outputs" / "consegne_2026_10_09"

# clienti per id pubblico (mai per nome libero) + nome atteso, per non confondere clienti simili
SPLASH = ("CLI-000010", "Splash")
AZUL = ("CLI-000005", "Azul y Sal")
CALLAO = ("CLI-000009", "El Callao")
ALCHIMIA = ("CLI-000003", "Alchimia Sushi")

# (ordine, riga, varieta', SET, semina di provenienza)
SPLASH_RIGHE = [("ORD-000044", "RO-000102", "Cilantro", "0.5", "SEM-000008"),
                ("ORD-000044", "RO-000103", "Basilico", "0.5", "SEM-000023")]
SPLASH_ORIGINALE = Decimal("1")        # quantita' attuale delle due righe, da portare a 0.5
AZUL_RIGA = ("ORD-000042", "RO-000100", "Cilantro", "2", "SEM-000008")
CALLAO_MANUALE = [("Afila", "1", "SEM-000010")]
ALCHIMIA_RIGHE = [("ORD-000040", "RO-000092", "Afila", "0.5", "SEM-000010"),
                  ("ORD-000040", "RO-000094", "Rabano", "0.5", "SEM-000015"),
                  ("ORD-000040", "RO-000095", "Hinojo", "0.5", "SEM-000005")]
# Hinojo esce dalla giacenza (SEM-000005 gia' raccolta il 2/10): niente raccolta
DA_GIACENZA = {"SEM-000005"}
MOTIVO_SPLASH = ("Splash ORD-000044: la prima meta' (Cilantro 0.5 + Basilico 0.5) e' gia' stata consegnata con "
                 "CON-000005 (5/10/2026), registrata senza legarla all'ordine; residuo da consegnare oggi 0.5 + 0.5 "
                 "(dichiarato da Matteo il 9/10/2026).")


def carica_base():
    spec = importlib.util.spec_from_file_location("consegne_giornata_base", BASE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.TAG, module.OGGI, module.WORK = TAG, OGGI, WORK
    return module


b = carica_base()
Stop = b.Stop
_n, _fold = b._n, b._fold


class Piano:
    """Cio' che si consegna oggi, con le quantita' (azul_cilantro parametrico)."""

    def __init__(self, azul_cilantro: str = "2", oltre_attesi: bool = False) -> None:
        self.azul = (AZUL_RIGA[0], AZUL_RIGA[1], AZUL_RIGA[2], azul_cilantro, AZUL_RIGA[4])
        self.oltre_attesi = oltre_attesi

    def raccolte(self) -> list[tuple[str, str, Decimal]]:
        """[(semina, varieta', SET)] aggregati per semina, esclusa la giacenza."""
        tot: dict[str, list] = {}
        voci = [(r[4], r[2], r[3]) for r in SPLASH_RIGHE + [self.azul] + ALCHIMIA_RIGHE]
        voci += [(s, v, q) for v, q, s in CALLAO_MANUALE]
        for semina, varieta, qty in voci:
            if semina in DA_GIACENZA:
                continue
            row = tot.setdefault(semina, [varieta, Decimal(0)])
            row[1] += Decimal(qty)
        return [(s, v, q) for s, (v, q) in tot.items()]


def cliente_ok(ctx, atteso: tuple[str, str]) -> None:
    row = ctx.one("SELECT denominazione FROM tpo.clienti WHERE public_id=%s", (atteso[0],))
    if not row or _fold(row[0]) != _fold(atteso[1]):
        raise b.Stop(f"cliente {atteso[0]}: a sistema {row and row[0]!r}, atteso {atteso[1]!r}. Non procedo.")


def info_riga(ctx, ordine, riga):
    return ctx.one("""
        SELECT o.public_id, o.stato::text, cl.public_id, v.denominazione, ro.quantita,
               (SELECT count(*) FROM tpo.righe_consegna rc JOIN tpo.consegne c ON c.id=rc.consegna_id
                 WHERE rc.riga_ordine_id=ro.id AND c.stato='CONSEGNATA'),
               ro.quantita - COALESCE((SELECT SUM(rc.quantita) FROM tpo.righe_consegna rc
                 JOIN tpo.consegne c ON c.id=rc.consegna_id
                 WHERE rc.riga_ordine_id=ro.id AND c.stato='CONSEGNATA'),0)
        FROM tpo.righe_ordine ro JOIN tpo.ordini o ON o.id=ro.ordine_id JOIN tpo.clienti cl ON cl.id=o.cliente_id
        JOIN tpo.varieta v ON v.id=ro.varieta_id WHERE ro.public_id=%s""", (riga,))


def controlla_riga(ctx, cliente, riga_def, *, quantita_ammesse=None):
    """La riga e' dell'ordine/cliente/varieta' attesi, aperta, con residuo sufficiente."""
    ordine, riga, varieta, qty, _ = riga_def
    info = info_riga(ctx, ordine, riga)
    if not info:
        raise b.Stop(f"{ordine}/{riga} inesistente.")
    o_pid, stato, cli, vden, quantita, consegnate, residuo = info
    if o_pid != ordine or cli != cliente[0] or _fold(vden) != _fold(varieta):
        raise b.Stop(f"{riga}: a sistema e' {o_pid} / {cli} / {vden}, atteso {ordine} / {cliente[0]} / {varieta}.")
    if stato not in ("APERTO", "PARZIALMENTE_EVASO"):
        raise b.Stop(f"{ordine} e' {stato}: non consegnabile.")
    ammesse = quantita_ammesse or [Decimal(quantita)]
    if Decimal(quantita) not in ammesse:
        raise b.Stop(f"{riga}: quantita' a sistema {_n(quantita)}, attese {', '.join(_n(a) for a in ammesse)}.")
    return Decimal(quantita), int(consegnate), Decimal(residuo)


def controlli(ctx, piano: Piano, da_fare: dict[str, bool]):
    print("== CONTROLLI")
    for tag, cli in (("splash", SPLASH), ("azul", AZUL), ("callao", CALLAO), ("alchimia", ALCHIMIA)):
        if da_fare[tag]:
            cliente_ok(ctx, cli)
            print(f"  cliente {cli[0]} = {cli[1]}")
    if da_fare["splash"]:
        for r in SPLASH_RIGHE:
            q, cons, _ = controlla_riga(ctx, SPLASH, r, quantita_ammesse=[SPLASH_ORIGINALE, Decimal(r[3])])
            if cons:
                raise b.Stop(f"{r[0]}/{r[1]} ha gia' consegne registrate: non la tocco, dimmi come procedere.")
            print(f"  {r[0]} {r[1]} {r[2]}: {_n(q)} SET a sistema -> consegno {r[3]}")
    if da_fare["azul"]:
        _, _, res = controlla_riga(ctx, AZUL, piano.azul)
        if res < Decimal(piano.azul[3]):
            raise b.Stop(f"{piano.azul[1]}: residuo {_n(res)} < {piano.azul[3]} SET.")
        print(f"  {piano.azul[0]} {piano.azul[1]} {piano.azul[2]}: residuo {_n(res)} SET -> consegno {piano.azul[3]} "
              f"(resta aperto {_n(res - Decimal(piano.azul[3]))})")
    if da_fare["alchimia"]:
        for r in ALCHIMIA_RIGHE:
            _, _, res = controlla_riga(ctx, ALCHIMIA, r)
            if res < Decimal(r[3]):
                raise b.Stop(f"{r[1]}: residuo {_n(res)} < {r[3]} SET.")
            print(f"  {r[0]} {r[1]} {r[2]}: residuo {_n(res)} SET -> consegno {r[3]}")
    if da_fare["alchimia"]:
        for _, riga, varieta, qty, semina in ALCHIMIA_RIGHE:
            if semina not in DA_GIACENZA:
                continue
            giac = b.giacenza_set(ctx, b.varieta_id(ctx, varieta))
            if giac < Decimal(qty):
                raise b.Stop(f"{varieta}: giacenza {_n(giac)} SET < {qty}.")
            print(f"  {varieta}: giacenza {_n(giac)} SET (esce da {semina}, nessuna raccolta)")


def modifica_splash(ctx, tx_factory):
    print("\n== SPLASH: ORD-000044 portato al residuo reale (prima meta' gia' consegnata con CON-000005)")
    spec = importlib.util.spec_from_file_location("modifica_ordine_script",
                                                  ROOT / "scripts" / "commissioning" / "2026-10-07_modifica_ordine.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    for ordine, riga, varieta, qty, _ in SPLASH_RIGHE:
        attuale = Decimal(info_riga(ctx, ordine, riga)[4])
        if attuale == Decimal(qty):
            print(f"  {riga} {varieta}: gia' {qty} SET, salto.")
            continue
        conn = tx_factory()
        try:
            rc = mod.run_quantita(conn, ordine, riga, Decimal(qty), MOTIVO_SPLASH, ctx.execute)
        finally:
            conn.close()
        if rc != 0:
            raise b.Stop(f"modifica {ordine} {riga} non riuscita (esito {rc}): non procedo.")


def raccolte(ctx, piano: Piano, t: datetime):
    print("\n== RACCOLTE E CARICHI A MAGAZZINO (solo i SET che escono oggi)")
    for semina, varieta, qty in piano.raccolte():
        qty = _n(qty)
        stato, _, attesi, uom, _, codice, raccolti = b.semina_row(ctx, semina, varieta)
        if stato != "PRONTA_ALLA_RACCOLTA":
            raise b.Stop(f"{semina} e' {stato}, non PRONTA_ALLA_RACCOLTA: dimmi come procedere.")
        ultimo = b.ultimo_evento(ctx, semina)
        if ultimo is not None and t <= ultimo:
            raise b.Stop(f"{semina}: la raccolta ({t:%H:%M}) non e' dopo l'ultimo evento ({ultimo:%Y-%m-%d %H:%M}).")
        done = b.audit_fatto(ctx, "RACCOLTA", f"{TAG}-raccolta-{semina}")
        giac = b.giacenza_set(ctx, b.varieta_id(ctx, varieta))
        if not done and giac != 0:
            raise b.Stop(f"{varieta}: giacenza {_n(giac)} SET diversa da 0 prima del carico: dimmi come procedere.")
        oltre = attesi is not None and Decimal(raccolti) + Decimal(qty) > Decimal(attesi)
        if not done and oltre and not piano.oltre_attesi:
            raise b.Stop(f"{semina}: {_n(raccolti)} gia' raccolti + {qty} = {_n(Decimal(raccolti) + Decimal(qty))} "
                         f"superano i {_n(attesi)} SET attesi dal sistema. Se hai davvero quei SET fisici (gli attesi "
                         "sono una stima) rilancia con --oltre-attesi; se no riduci la quantita'.")
        print(f"\n{varieta}: {qty} SET da {semina} ({codice}); giacenza {_n(giac)}; gia' raccolti {_n(raccolti)} "
              f"su {_n(attesi) if attesi is not None else '?'}"
              + ("  [raccolta gia' registrata]" if done else "")
              + ("  [OLTRE gli attesi: dichiarato da Matteo]" if oltre and piano.oltre_attesi else ""))
        note = f"Raccolta {varieta} {qty} SET ({semina}) dichiarata da Matteo il 9/10/2026"
        if oltre:
            note += f" (oltre i {_n(attesi)} SET attesi: quantita' fisica dichiarata dal titolare)"
        out = ctx.tpo(["raccolta", "record", "--semina", semina, "--quantity", qty, "--uom", "SET",
                       "--effective-at", t.isoformat(), "--notes", note, "--actor", b.ACTOR, "--reason", note,
                       "--correlation-id", f"{TAG}-raccolta-{semina}",
                       "--idempotency-key", f"{TAG}-raccolta-{semina}", "--confirm"], f"raccolta {varieta}")
        racc = b.kv(out, "RACCOLTA_ID") or "RAC-??????(da anteprima)"
        motivo = f"Carico magazzino da raccolta {varieta} {qty} SET ({semina})"
        ctx.tpo(["movimento", "carica-raccolta", "--raccolta", racc, "--unita-misura", "SET", "--effective-at",
                 t.isoformat(), "--motivo", motivo, "--actor", b.ACTOR, "--reason", motivo,
                 "--correlation-id", f"{TAG}-carico-{semina}", "--idempotency-key", f"{TAG}-carico-{semina}",
                 "--confirm"], f"carico {racc} ({varieta})")


def righe_esistenti(ctx, defs):
    out = []
    for ordine, riga, varieta, qty, semina in defs:
        ov, rv = b.versioni(ctx, ordine, riga)
        out.append({"order_id": ordine, "order_line_id": riga, "quantity": qty, "unit": "SET",
                    "expected_order_version": ov, "expected_order_line_version": rv, "semina": semina})
    return out


def consegne(ctx, piano: Piano, t: datetime, da_fare: dict[str, bool]):
    eff = t.isoformat()
    print("\n== SPLASH")
    if not da_fare["splash"]:
        print("  consegna gia' registrata: salto.")
    elif not ctx.execute:
        print("  (anteprima) consegna: Cilantro 0.5 (SEM-000008) + Basilico 0.5 (SEM-000023) su ORD-000044")
    else:
        con = b.consegna(ctx, SPLASH[0], "2026-10-06", eff, righe_esistenti(ctx, SPLASH_RIGHE), "splash",
                         "Consegna a Splash del 9/10/2026: Cilantro 0.5 + Basilico 0.5 SET (ORD-000044, seconda meta')")
        b.bolla(ctx, con)

    print("\n== AZUL Y SAL")
    if not da_fare["azul"]:
        print("  consegna gia' registrata: salto.")
    elif not ctx.execute:
        print(f"  (anteprima) consegna: Cilantro {piano.azul[3]} (SEM-000008) su ORD-000042")
    else:
        con = b.consegna(ctx, AZUL[0], OGGI, eff, righe_esistenti(ctx, [piano.azul]), "azul",
                         f"Consegna a Azul y Sal del 9/10/2026: Cilantro {piano.azul[3]} SET (ORD-000042)")
        b.bolla(ctx, con)

    print("\n== EL CALLAO (occasionale)")
    if not da_fare["callao"]:
        print("  consegna gia' registrata: salto.")
    else:
        ord_man, righe_man = b.ordine_manuale(
            ctx, CALLAO[0], CALLAO_MANUALE, "callao",
            "Vendita a El Callao del 9/10/2026: Afila 1 SET (cliente trattato come occasionale, fuori dal programma)")
        if ord_man is None:
            print("  (anteprima) consegna: Afila 1 (SEM-000010) su nuovo ordine manuale")
        else:
            con = b.consegna(ctx, CALLAO[0], OGGI, eff, b.righe_consegna(ctx, ord_man, righe_man, CALLAO_MANUALE),
                             "callao", "Consegna a El Callao del 9/10/2026: Afila 1 SET")
            b.bolla(ctx, con)

    print("\n== ALCHIMIA SUSHI")
    if not da_fare["alchimia"]:
        print("  consegna gia' registrata: salto.")
    elif not ctx.execute:
        print("  (anteprima) consegna su ORD-000040: Afila 0.5 (SEM-000010) + Rabano 0.5 (SEM-000015) + "
              "Hinojo 0.5 (giacenza, SEM-000005). Mizuna 0.5 resta aperta.")
    else:
        con = b.consegna(ctx, ALCHIMIA[0], OGGI, eff, righe_esistenti(ctx, ALCHIMIA_RIGHE), "alchimia",
                         "Consegna a Alchimia Sushi del 9/10/2026: Afila 0.5, Rabano 0.5, Hinojo 0.5 SET (ORD-000040)")
        b.bolla(ctx, con)


def fase_consegne(ctx, piano: Piano, t: datetime, tx_factory):
    ctx.check_head()
    da_fare = {tag: not b.audit_fatto(ctx, "CONSEGNA", f"{TAG}-consegna-{tag}")
               for tag in ("splash", "azul", "callao", "alchimia")}
    controlli(ctx, piano, da_fare)
    if da_fare["splash"]:
        modifica_splash(ctx, tx_factory)
    raccolte(ctx, piano, t)
    consegne(ctx, piano, t, da_fare)


def tx_factory_default():
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    return psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"], password=p["password"],
                           sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    ap.add_argument("--effective-at", help="istante ISO 8601 (default: adesso, salvato al primo --esegui)")
    ap.add_argument("--azul-cilantro", default="2", help="SET di Cilantro per Azul y Sal (default 2)")
    ap.add_argument("--oltre-attesi", action="store_true", help="consente raccolte oltre i SET attesi dal sistema")
    ap.add_argument("--pdf-dir", default=str(b.PDF_DIR_DEFAULT))
    a = ap.parse_args()
    t = b.instant("consegne", a.esegui, a.effective_at)
    ctx = b.Ctx(a.esegui, Path(a.pdf_dir))
    try:
        print(f"== CONSEGNE 9/10/2026 -- {'ESECUZIONE' if a.esegui else 'ANTEPRIMA (nulla viene scritto)'} "
              f"(istante {t.isoformat()})")
        fase_consegne(ctx, Piano(a.azul_cilantro, a.oltre_attesi), t, tx_factory_default)
        print("\n== FINE")
        return 0
    except b.Stop as exc:
        print(f"\nSTOP: {exc}", file=sys.stderr)
        return 1
    finally:
        ctx.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
