"""Revisiona un protocollo agronomico: nuova versione N+1 al posto della corrente (7/10/2026, richiesta di Matteo).

Sempre in ANTEPRIMA finche' non aggiungi --esegui; tutto o niente (una transazione). La versione corrente viene
CHIUSA alla data di validita' della nuova (unica modifica ammessa su una versione esistente); la nuova eredita tutti
i campi tranne quelli dichiarati. Non e' retroattiva. Le semine gia' avviate restano sulla versione con cui sono
partite e le loro finestre di raccolta gia' compilate NON cambiano.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-07_revisiona_protocollo.py Rabano --germinazione 5 --luce 3 \\
      --motivo "Tempi reali di campo: 5 giorni di germinazione + 3 di luce completi" [--valido-dal 2026-10-08]
  ... --esegui    per scrivere davvero

Campi revisionabili: --germinazione, --luce, --idratazione-ore, --g-per-set, --resa, --granularita, --lead-min,
--lead-max, --buffer-minuti, --ora-semina (HH:MM), --ora-raccolta (HH:MM). Quelli non indicati restano come nella
versione corrente. --evidenza sostituisce l'evidenza (altrimenti resta quella della versione corrente).
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

from src.tpo_core.infrastructure.postgresql.protocol_revision import (  # noqa: E402
    ProtocolRevisionError, prepare, revise,
)

ACTOR = "matteo"
PROVENANCE = "commissioning:2026-10-07_revisiona_protocollo"
TIMEZONE = ZoneInfo("Atlantic/Canary")

LABELS = {
    "hydration_hours": "idratazione (ore)", "germination_days": "germinazione (giorni)",
    "light_growth_days": "luce (giorni)", "seed_grams_per_set": "grammi seme per SET",
    "expected_yield": "resa attesa (SET)", "production_granularity": "granularita' (SET)",
    "harvest_min_lead_days": "anticipo raccolta min (giorni)", "harvest_max_lead_days": "anticipo raccolta max (giorni)",
    "temporal_buffer_minutes": "buffer (minuti)", "planned_sowing_time": "ora semina",
    "target_harvest_time": "ora raccolta",
}
COLUMN_OF = {
    "hydration_hours": "idratazione_ore", "germination_days": "germinazione_giorni",
    "light_growth_days": "crescita_luce_giorni", "seed_grams_per_set": "grammi_seme_per_set",
    "expected_yield": "resa_attesa", "production_granularity": "granularita_produttiva",
    "harvest_min_lead_days": "harvest_min_lead_giorni", "harvest_max_lead_days": "harvest_max_lead_giorni",
    "temporal_buffer_minutes": "buffer_temporale_minuti", "planned_sowing_time": "orario_semina_previsto",
    "target_harvest_time": "orario_raccolta_target",
}


def _fmt(value) -> str:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if hasattr(value, "isoformat") and not isinstance(value, (date, datetime)):
        return value.strftime("%H:%M")
    return str(value)


def today_local() -> date:
    return datetime.now(TIMEZONE).date()


def run(conn, variety: str, changes: dict, valid_from: date | None, reason: str, evidence: str | None,
        esegui: bool, today: date | None = None, out=print) -> int:
    today = today or today_local()
    valid_from = valid_from or today
    cur = conn.cursor()
    try:
        revision = prepare(cur, variety, changes, valid_from, today)
    except ProtocolRevisionError as exc:
        conn.rollback()
        out(f"RIFIUTATO, nulla scritto: {exc}")
        return 2
    old = revision.old
    merged = {**old, **revision.new_values}
    cycle_old = old["germinazione_giorni"] + old["crescita_luce_giorni"]
    cycle_new = merged["germinazione_giorni"] + merged["crescita_luce_giorni"]
    out(f"== REVISIONE PROTOCOLLO {revision.variety} ({'ESECUZIONE' if esegui else 'ANTEPRIMA, NULLA VIENE SCRITTO'})")
    out(f"Versione corrente {old['public_id']} (v{old['numero_versione']}, valida dal {old['valida_dal']}) "
        f"-> nuova {revision.new_public_id} (v{old['numero_versione'] + 1}, valida dal {revision.valid_from})")
    out(f"\n{'CAMPO':34}{'DA':>10}{'A':>10}")
    for name, (before, after) in revision.changes.items():
        out(f"{LABELS[name]:34}{_fmt(before):>10}{_fmt(after):>10}")
    out(f"\nCiclo (germinazione + luce): {cycle_old} -> {cycle_new} giorni")
    out(f"Tutti gli altri campi restano come in {old['public_id']}.")
    out(f"\nLa versione {old['public_id']} viene chiusa al {revision.valid_from} (esclusa): fino al giorno prima "
        "vale la vecchia, da quel giorno la nuova.")
    if revision.open_semine:
        listed = ", ".join(f"{sem} ({state})" for sem, state in revision.open_semine)
        out(f"\nSemine ancora aperte sulla versione vecchia: {listed}")
        out("  -> restano sulla versione con cui sono partite; le loro finestre di raccolta gia' compilate "
            "NON cambiano.")
    else:
        out("\nNessuna semina aperta sulla versione vecchia.")
    out("Le semine create dal giorno di validita' in poi (e il planner) usano la nuova versione.")
    out(f"\nMotivo registrato: {reason}")
    if evidence:
        out(f"Evidenza: {evidence}")
    if not esegui:
        conn.rollback()
        out("\nANTEPRIMA: nulla e' stato scritto. Per eseguire aggiungi --esegui")
        return 0
    try:
        revision = revise(
            cur, variety=variety, changes=changes, valid_from=revision.valid_from, today=today, actor=ACTOR,
            reason=reason, evidence=evidence,
            correlation_id=f"revisiona-protocollo-{old['public_id']}-{revision.valid_from}-{uuid.uuid4().hex[:8]}",
            provenance=PROVENANCE)
        conn.commit()
    except ProtocolRevisionError as exc:
        conn.rollback()
        out(f"RIFIUTATO, nulla scritto: {exc}")
        return 2
    except Exception as exc:  # tutto o niente
        conn.rollback()
        out(f"ERRORE, annullato tutto (nulla scritto): {exc}")
        return 1
    out(f"\nFATTO: {revision.new_public_id} creata (APPROVATA, dal {revision.valid_from}); "
        f"{old['public_id']} chiusa al {revision.valid_from}.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("varieta", help="nome varieta' (es. Rabano)")
    ap.add_argument("--germinazione", type=int)
    ap.add_argument("--luce", type=int)
    ap.add_argument("--idratazione-ore")
    ap.add_argument("--g-per-set")
    ap.add_argument("--resa")
    ap.add_argument("--granularita")
    ap.add_argument("--lead-min", type=int)
    ap.add_argument("--lead-max", type=int)
    ap.add_argument("--buffer-minuti", type=int)
    ap.add_argument("--ora-semina", help="HH:MM")
    ap.add_argument("--ora-raccolta", help="HH:MM")
    ap.add_argument("--valido-dal", help="AAAA-MM-GG (default: oggi)")
    ap.add_argument("--motivo", required=True)
    ap.add_argument("--evidenza")
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    a = ap.parse_args()
    changes = {
        "germination_days": a.germinazione, "light_growth_days": a.luce, "hydration_hours": a.idratazione_ore,
        "seed_grams_per_set": a.g_per_set, "expected_yield": a.resa, "production_granularity": a.granularita,
        "harvest_min_lead_days": a.lead_min, "harvest_max_lead_days": a.lead_max,
        "temporal_buffer_minutes": a.buffer_minuti, "planned_sowing_time": a.ora_semina,
        "target_harvest_time": a.ora_raccolta,
    }
    changes = {k: v for k, v in changes.items() if v is not None}
    if not changes:
        raise SystemExit("STOP: indica almeno un campo da cambiare (es. --germinazione 5 --luce 3).")
    from secret_boundary import load_postgresql_parameters
    import psycopg
    p = load_postgresql_parameters()
    conn = psycopg.connect(host=p["host"], port=p["port"], dbname=p["dbname"], user=p["user"],
                           password=p["password"], sslmode=p["sslmode"], connect_timeout=p["connect_timeout"])
    try:
        return run(conn, a.varieta, changes, date.fromisoformat(a.valido_dal) if a.valido_dal else None,
                   a.motivo, a.evidenza, a.esegui)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
