"""Controllo di SALUTE del sistema TPO -- SOLA LETTURA, non scrive nulla.

Uso (dalla cartella del progetto):
    .venv/bin/python scripts/commissioning/2026-10-05_check_sistema.py

Verifica: connessione DB e SSL, revisione alembic = ultima migrazione del
repository, contatori id_sequences oltre il massimo reale, giacenze (varieta'
e articoli) non negative (articoli: anche coerenti col registro dei movimenti), lotti seme
non negativi, ogni movimento con il suo audit, semine non chiuse (con
anzianita'), ordini aperti/consegne in corso, stato git (commit non pushati).
Esito: OK / ATTENZIONE (da guardare) / ERRORE (da sistemare). Exit 0 se
nessun ERRORE.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters  # noqa: E402
import psycopg  # noqa: E402

risultati = []  # (livello, titolo, dettaglio)


def esito(livello, titolo, dettaglio=""):
    risultati.append((livello, titolo, dettaglio))
    icona = {"OK": "OK         ", "ATTENZIONE": "ATTENZIONE ", "ERRORE": "ERRORE     "}[livello]
    print(f"[{icona}] {titolo}" + (f"\n             {dettaglio}" if dettaglio else ""))


def sezione(t):
    print(f"\n== {t}")


def head_migrazioni():
    revs, downs = {}, set()
    for f in (ROOT / "migrations" / "versions").glob("*.py"):
        s = f.read_text(encoding="utf-8")
        r = re.search(r"^revision\s*(?::[^=]+)?=\s*['\"]([^'\"]+)['\"]", s, re.M)
        d = re.search(r"^down_revision\s*(?::[^=]+)?=\s*(?:['\"]([^'\"]+)['\"]|None)", s, re.M)
        if r:
            revs[r.group(1)] = f.name
            if d and d.group(1):
                downs.add(d.group(1))
    teste = [r for r in revs if r not in downs]
    return teste


def main():
    p = load_postgresql_parameters()
    sezione("1. Database")
    try:
        conn = psycopg.connect(
            host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
            password=p["password"], sslmode=p["sslmode"], connect_timeout=p["connect_timeout"],
            autocommit=True)
    except Exception as exc:  # noqa: BLE001
        esito("ERRORE", "Connessione al database", f"{type(exc).__name__}: {exc}")
        return 1
    cur = conn.cursor()
    try:
        cur.execute("SELECT now(), current_setting('server_version')")
        ora, ver = cur.fetchone()
        ssl = conn.pgconn.ssl_in_use  # verifica lato client (libpq): vale anche dietro un pooler
        proto = ""
        try:
            proto = conn.pgconn.ssl_attribute(b"protocol").decode()
        except Exception:  # noqa: BLE001
            pass
        esito("OK" if ssl else "ERRORE", f"Connesso (PostgreSQL {ver}, ora server {ora:%Y-%m-%d %H:%M} UTC, "
              f"sslmode={p['sslmode']}, cifratura {proto or 'attiva' if ssl else 'ASSENTE'})",
              "" if ssl else "connessione NON cifrata")

        cur.execute("SELECT version_num FROM public.alembic_version")
        applicate = [r[0] for r in cur.fetchall()]
        teste = head_migrazioni()
        if sorted(applicate) == sorted(teste):
            esito("OK", f"Migrazioni allineate (alembic {', '.join(applicate)})")
        else:
            esito("ERRORE", "Migrazioni NON allineate",
                  f"database: {applicate}; ultima nel repository: {teste}")

        sezione("2. Contatori identita'")
        controlli = [("ORDINE_ID", "tpo.ordini", "ORD"), ("RIGA_ORDINE_ID", "tpo.righe_ordine", "RO"),
                     ("MOVIMENTO_ID", "tpo.movimenti_magazzino", "MOV"), ("CONSEGNA_ID", "tpo.consegne", "CON"),
                     ("RACCOLTA_ID", "tpo.raccolte", "RAC"), ("ARTICOLO_ID", "tpo.articoli", "ART")]
        cattivi = []
        for seq, tabella, pre in controlli:
            cur.execute("SELECT next_value FROM tpo.id_sequences WHERE sequence_name=%s", (seq,))
            r = cur.fetchone()
            cur.execute(f"SELECT coalesce(max(substring(public_id from '[0-9]+$')::int), 0) FROM {tabella}")
            mx = cur.fetchone()[0]
            if r is None:
                cattivi.append(f"{seq}: contatore mancante")
            elif r[0] <= mx:
                cattivi.append(f"{seq}: prossimo {r[0]} <= massimo usato {mx}")
        esito("ERRORE" if cattivi else "OK", "Contatori sopra il massimo gia' usato (" +
              ", ".join(c[0].replace("_ID", "") for c in controlli) + ")", "; ".join(cattivi))

        sezione("3. Magazzino")
        cur.execute("""SELECT v.public_id, v.denominazione, s.unita_misura::text, s.disponibile,
              coalesce((SELECT sum(CASE WHEN m.direzione='POSITIVO' THEN m.quantita ELSE -m.quantita END)
                        FROM tpo.movimenti_magazzino m WHERE m.varieta_id=s.varieta_id
                        AND m.unita_misura=s.unita_misura),0)
              FROM tpo.stock s JOIN tpo.varieta v ON v.id=s.varieta_id ORDER BY v.public_id""")
        righe = cur.fetchall()
        neg = [f"{r[1]} {r[3]} {r[2]}" for r in righe if r[3] < 0]
        esito("ERRORE" if neg else "OK", "Giacenze varieta' mai negative", "; ".join(neg))
        for r in righe:
            if r[3] != 0:
                print(f"             {r[1]:<14} {r[3]:>10} {r[2]}")
        cur.execute("""SELECT a.public_id, a.denominazione, s.disponibile,
              coalesce((SELECT sum(CASE WHEN m.direzione='POSITIVO' THEN m.quantita ELSE -m.quantita END)
                        FROM tpo.movimenti_magazzino m WHERE m.articolo_id=s.articolo_id),0)
              FROM tpo.stock_articoli s JOIN tpo.articoli a ON a.id=s.articolo_id ORDER BY a.public_id""")
        art = cur.fetchall()
        bad = [f"{r[1]}: giacenza {r[2]} vs registro {r[3]}" for r in art if r[2] != r[3] or r[2] < 0]
        esito("ERRORE" if bad else "OK", "Giacenze articoli (substrato, vaschette) coerenti e non negative", "; ".join(bad))
        for r in art:
            print(f"             {r[1]:<14} {r[2]:>10} pezzi")
        cur.execute("SELECT public_id, quantita_residua FROM tpo.lotti_seme WHERE quantita_residua < 0")
        neg = cur.fetchall()
        esito("ERRORE" if neg else "OK", "Lotti seme: nessun residuo negativo", "; ".join(f"{a} {b}" for a, b in neg))
        # i movimenti nati da una CONSEGNA sono auditati insieme alla consegna (entity CONSEGNA)
        SENZA_AUDIT = """NOT EXISTS (SELECT 1 FROM tpo.audit_eventi a WHERE a.entity_type='MOVIMENTO_MAGAZZINO'
                          AND a.entity_public_id=m.public_id)
                         AND NOT (m.origine_tipo='CONSEGNA' AND EXISTS (
                          SELECT 1 FROM tpo.consegne c JOIN tpo.audit_eventi a2 ON a2.entity_type='CONSEGNA'
                          AND a2.entity_public_id=c.public_id WHERE c.id=m.consegna_id))"""
        cur.execute(f"SELECT count(*) FROM tpo.movimenti_magazzino m WHERE {SENZA_AUDIT}")
        senza = cur.fetchone()[0]
        det = ""
        if senza:
            cur.execute(f"""SELECT m.public_id, m.tipo::text, m.origine_tipo, m.data_movimento::date,
                                  coalesce(v.denominazione, a.denominazione), m.quantita, m.unita_misura::text
                           FROM tpo.movimenti_magazzino m
                           LEFT JOIN tpo.varieta v ON v.id=m.varieta_id LEFT JOIN tpo.articoli a ON a.id=m.articolo_id
                           WHERE {SENZA_AUDIT} ORDER BY m.id""")
            det = "; ".join(f"{r[0]} {r[1]} {r[2]} {r[3]} {r[4]} {r[5]} {r[6]}" for r in cur.fetchall())
        esito("ATTENZIONE" if senza else "OK", "Ogni movimento ha il suo audit (direttamente o tramite la consegna)",
              f"{senza} senza audit: {det}" if senza else "")
        cur.execute("""SELECT m.public_id, m.tipo::text, m.direzione::text, m.data_movimento::date, v.denominazione,
                              m.quantita, m.unita_misura::text, m.origine_tipo FROM tpo.movimenti_magazzino m
                       JOIN tpo.varieta v ON v.id=m.varieta_id
                       WHERE m.created_at > now() - interval '4 days' ORDER BY m.id""")
        rec = cur.fetchall()
        print("             movimenti varieta' registrati negli ultimi 4 giorni:")
        for r in rec:
            print(f"               {r[0]} {r[1]:<9} {r[2]:<8} {r[3]} {r[4]:<10} {r[5]:>9} {r[6]} ({r[7]})")
        if not rec:
            print("               (nessuno)")

        sezione("4. Produzione")
        cur.execute("""SELECT s.stato::text, count(*), min(s.data_avvio::date), max(s.data_avvio::date)
                       FROM tpo.semine s WHERE s.stato <> 'CHIUSA' GROUP BY 1 ORDER BY 1""")
        stati = cur.fetchall()
        esito("OK", f"Semine non chiuse: {sum(r[1] for r in stati)}",
              "; ".join(f"{r[0]} {r[1]} (dal {r[2]} al {r[3]})" for r in stati))
        cur.execute("""SELECT s.public_id, v.denominazione, s.stato::text, now()::date - s.data_avvio::date
                       FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id
                       WHERE s.stato <> 'CHIUSA' AND now()::date - s.data_avvio::date > 21 ORDER BY 4 DESC""")
        vecchie = cur.fetchall()
        esito("ATTENZIONE" if vecchie else "OK", "Nessuna semina non chiusa da oltre 21 giorni",
              "; ".join(f"{a} {b} {c} da {d} gg" for a, b, c, d in vecchie))

        sezione("5. Ordini e consegne")
        cur.execute("""SELECT o.public_id, cl.denominazione, o.stato::text, o.data_consegna_prevista, o.tipo_creazione::text
                       FROM tpo.ordini o JOIN tpo.clienti cl ON cl.id=o.cliente_id
                       WHERE o.stato IN ('APERTO','PARZIALMENTE_EVASO')
                       ORDER BY o.data_consegna_prevista, o.public_id""")
        aperti = cur.fetchall()
        manuali = [r for r in aperti if r[4] == "MANUALE"]
        sched = [r for r in aperti if r[4] != "MANUALE"]
        sched_ritardo = [r for r in sched if r[3] is not None and r[3] < ora.date()]
        man_ritardo = [r for r in manuali if r[3] is not None and r[3] < ora.date()]
        esito("ATTENZIONE" if man_ritardo else "OK", f"Ordini MANUALI aperti: {len(manuali)}"
              + (f", in ritardo: {len(man_ritardo)}" if man_ritardo else ""),
              "; ".join(f"{r[0]} {r[1]} ({r[3]})" for r in man_ritardo))
        for r in manuali:
            print(f"             {r[0]} {r[1]:<28} {r[2]:<18} prevista {r[3]}")
        per_cliente = {}
        for r in sched_ritardo:
            per_cliente.setdefault(r[1], []).append(r[3])
        esito("ATTENZIONE" if sched_ritardo else "OK",
              f"Ordini generati dallo scheduler ancora aperti: {len(sched)} (di cui oltre la data prevista: {len(sched_ritardo)})",
              "per cliente: " + ", ".join(f"{c} {len(d)} (dal {min(d)})" for c, d in sorted(per_cliente.items()))
              if sched_ritardo else "")
        cur.execute("SELECT public_id, state::text, started_at, ordini_generati FROM tpo.runs ORDER BY id DESC LIMIT 1")
        r = cur.fetchone()
        if r:
            giorni = (ora - r[2]).days
            esito("ATTENZIONE" if giorni > 2 or r[1] == "FAILED" else "OK",
                  f"Ultimo run scheduling ordini: {r[0]} {r[1]} il {r[2]:%Y-%m-%d} ({giorni} gg fa, {r[3]} ordini generati)")
        else:
            esito("ATTENZIONE", "Nessun run dello scheduling ordini registrato")
        cur.execute("SELECT public_id, state::text, started_at FROM tpo.production_planning_runs ORDER BY id DESC LIMIT 1")
        r = cur.fetchone()
        if r:
            giorni = (ora - r[2]).days
            esito("ATTENZIONE" if giorni > 2 or r[1] == "FAILED" else "OK",
                  f"Ultimo run piano di produzione: {r[0]} {r[1]} il {r[2]:%Y-%m-%d} ({giorni} gg fa)")
        else:
            esito("ATTENZIONE", "Nessun run del piano di produzione registrato")
        cur.execute("""SELECT c.stato::text, count(*) FROM tpo.consegne c GROUP BY 1 ORDER BY 1""")
        print("             consegne per stato: " + ", ".join(f"{a} {b}" for a, b in cur.fetchall()))
        cur.execute("""SELECT c.public_id FROM tpo.consegne c WHERE c.stato='CONSEGNATA' AND NOT EXISTS
                       (SELECT 1 FROM tpo.righe_consegna rc WHERE rc.consegna_id=c.id)""")
        vuote = [r[0] for r in cur.fetchall()]
        esito("ERRORE" if vuote else "OK", "Nessuna consegna consegnata senza righe", ", ".join(vuote))
    finally:
        conn.close()

    sezione("6. Codice (git)")
    def git(*a):
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    ramo = git("rev-parse", "--abbrev-ref", "HEAD")
    ultimo = git("log", "-1", "--format=%h %s")
    non_pushati = git("log", "@{u}..", "--oneline")
    modificati = [l for l in git("status", "--short").splitlines() if not l.startswith("??")]
    esito("OK", f"Ramo {ramo}, ultimo commit: {ultimo}")
    esito("ATTENZIONE" if non_pushati else "OK", "Commit tutti pushati", non_pushati)
    esito("ATTENZIONE" if modificati else "OK", "Nessun file tracciato modificato non committato",
          "; ".join(modificati))

    print("\n== RIEPILOGO")
    for livello in ("ERRORE", "ATTENZIONE", "OK"):
        print(f"{livello:<11}: {sum(1 for r in risultati if r[0] == livello)}")
    return 1 if any(r[0] == "ERRORE" for r in risultati) else 0


if __name__ == "__main__":
    raise SystemExit(main())
