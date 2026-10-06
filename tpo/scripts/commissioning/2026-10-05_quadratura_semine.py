"""Quadratura SEMINE / STOCK / ORDINI / PIANO per varieta' — SOLA LETTURA (5/10/2026).
Risponde a: "ordini e semine sono in pari?". Per ogni varieta' (tutto in SET):
  domanda aperta  = ordinato - consegnato sugli ordini APERTO/PARZIALMENTE_EVASO
  offerta         = stock a magazzino + semine in corso (resa utile attesa, non chiuse)
  piano corrente  = ultima revisione viva: quanto copre stock / semine in corso / raccolte e quanto resta
                    DA SEMINARE (righe PIANIFICATA/PRONTA/TARDIVA con residuo da avviare)
Poi l'elenco delle semine in corso (stato, resa attesa, finestra di raccolta) e il da-seminare con le date.
Non scrive nulla.

Uso: .venv/bin/python scripts/commissioning/2026-10-05_quadratura_semine.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

LATEST_REV = ("SELECT r.id FROM tpo.piano_produzione_revisioni r WHERE r.sostituita_at IS NULL "
              "ORDER BY r.created_at DESC LIMIT 1")


def table(cur, title, header, sql, args=(), out=print):
    out(f"\n== {title}")
    out(header)
    cur.execute(sql, args)
    rows = cur.fetchall()
    for r in rows:
        out(" | ".join("-" if x is None else (f"{x:f}" if hasattr(x, "as_tuple") else str(x)) for x in r))
    if not rows:
        out("(nessuna riga)")
    return rows


def run(conn, out=print) -> int:
    cur = conn.cursor()
    cur.execute(f"SELECT public_id, created_at::timestamp(0) FROM tpo.piano_produzione_revisioni "
                f"WHERE id=({LATEST_REV})")
    rev = cur.fetchone()
    out(f"Revisione di piano viva piu' recente: {rev[0] if rev else '-'} (creata {rev[1] if rev else '-'})")
    table(cur, "QUADRO PER VARIETA' (SET)",
          "varieta | domanda aperta | stock | semine in corso (resa attesa) | piano: da stock | piano: da semine in corso "
          "| piano: da raccolte | piano: DA SEMINARE | semina piu' vicina",
          f"""
WITH dom AS (
  SELECT ro.varieta_id, SUM(ro.quantita - COALESCE((SELECT SUM(rc.quantita) FROM tpo.righe_consegna rc
         JOIN tpo.consegne c ON c.id=rc.consegna_id WHERE rc.riga_ordine_id=ro.id AND c.stato='CONSEGNATA'),0)) q
  FROM tpo.righe_ordine ro JOIN tpo.ordini o ON o.id=ro.ordine_id
  WHERE o.stato IN ('APERTO','PARZIALMENTE_EVASO') AND ro.unita_misura='SET' GROUP BY ro.varieta_id),
stk AS (SELECT varieta_id, SUM(disponibile) q FROM tpo.stock WHERE unita_misura='SET' GROUP BY varieta_id),
inc AS (SELECT varieta_id, SUM(expected_useful_quantity) q FROM tpo.semine
        WHERE stato<>'CHIUSA' AND expected_useful_uom='SET' GROUP BY varieta_id),
cov AS (
  SELECT rps.varieta_id,
         SUM(a.quantity) FILTER (WHERE a.allocation_type='STOCK') s,
         SUM(a.quantity) FILTER (WHERE a.allocation_type='PRODUZIONE_IN_CORSO') p,
         SUM(a.quantity) FILTER (WHERE a.allocation_type='RACCOLTA') h
  FROM tpo.allocazioni a JOIN tpo.righe_piano_semina rps ON rps.id=a.riga_piano_semina_id
  JOIN tpo.righe_ordine ro ON ro.id=rps.riga_ordine_id JOIN tpo.ordini o ON o.id=ro.ordine_id
  WHERE a.state='ATTIVA' AND rps.piano_revisione_id=({LATEST_REV})
    AND o.stato IN ('APERTO','PARZIALMENTE_EVASO') GROUP BY rps.varieta_id),
sow AS (
  SELECT rps.varieta_id, SUM(rps.quantita_residua_da_avviare) q, MIN(rps.sowing_at)::date d
  FROM tpo.righe_piano_semina rps JOIN tpo.righe_ordine ro ON ro.id=rps.riga_ordine_id
  JOIN tpo.ordini o ON o.id=ro.ordine_id
  WHERE rps.piano_revisione_id=({LATEST_REV}) AND rps.stato IN ('PIANIFICATA','PRONTA','TARDIVA')
    AND rps.quantita_residua_da_avviare>0 AND o.stato IN ('APERTO','PARZIALMENTE_EVASO') GROUP BY rps.varieta_id)
SELECT v.denominazione, COALESCE(dom.q,0), COALESCE(stk.q,0), COALESCE(inc.q,0),
       COALESCE(cov.s,0), COALESCE(cov.p,0), COALESCE(cov.h,0), COALESCE(sow.q,0), sow.d
FROM tpo.varieta v LEFT JOIN dom ON dom.varieta_id=v.id LEFT JOIN stk ON stk.varieta_id=v.id
LEFT JOIN inc ON inc.varieta_id=v.id LEFT JOIN cov ON cov.varieta_id=v.id LEFT JOIN sow ON sow.varieta_id=v.id
WHERE COALESCE(dom.q,0)+COALESCE(stk.q,0)+COALESCE(inc.q,0)+COALESCE(sow.q,0) > 0
ORDER BY v.denominazione""", out=out)
    table(cur, "SEMINE IN CORSO (non chiuse)",
          "semina | varieta | stato | avvio | resa attesa | finestra raccolta | allocata a ordini (piano vivo)",
          f"""
SELECT s.public_id, v.denominazione, s.stato::text, s.data_avvio::date,
       COALESCE(s.expected_useful_quantity::text||' '||s.expected_useful_uom::text,'(non definita)'),
       COALESCE(s.harvest_window_start::date::text||' -> '||s.harvest_window_end::date::text,'-'),
       COALESCE((SELECT SUM(a.quantity) FROM tpo.allocazioni a JOIN tpo.allocazioni_produzione_in_corso aip
                 ON aip.allocation_id=a.id JOIN tpo.righe_piano_semina rps ON rps.id=a.riga_piano_semina_id
                 WHERE aip.semina_id=s.id AND a.state='ATTIVA' AND rps.piano_revisione_id=({LATEST_REV})),0)
FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id WHERE s.stato<>'CHIUSA'
ORDER BY v.denominazione, s.data_avvio""", out=out)
    table(cur, "DA SEMINARE secondo il piano vivo (per data di semina)",
          "data semina | varieta | SET da avviare | per ordine | consegna | stato riga",
          f"""
SELECT rps.sowing_at::date, v.denominazione, rps.quantita_residua_da_avviare, o.public_id,
       rps.data_consegna, rps.stato
FROM tpo.righe_piano_semina rps JOIN tpo.varieta v ON v.id=rps.varieta_id
JOIN tpo.righe_ordine ro ON ro.id=rps.riga_ordine_id JOIN tpo.ordini o ON o.id=ro.ordine_id
WHERE rps.piano_revisione_id=({LATEST_REV}) AND rps.stato IN ('PIANIFICATA','PRONTA','TARDIVA')
  AND rps.quantita_residua_da_avviare>0 AND o.stato IN ('APERTO','PARZIALMENTE_EVASO')
ORDER BY rps.sowing_at, v.denominazione, o.public_id""", out=out)
    out("\nLettura: se 'DA SEMINARE' > 0 per una varieta', mancano semine per coprire gli ordini aperti; "
        "se 'semine in corso' supera 'piano: da semine in corso', una parte della resa non e' assegnata a nessun ordine.")
    conn.rollback()
    return 0


def main() -> int:
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return run(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
