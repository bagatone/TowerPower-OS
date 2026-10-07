"""SOLA LETTURA - "piano ipotetico": cosa c'e' da seminare, con la produzione in corso, SENZA scrivere nulla.

Usa il planner vero sui dati veri (stesso lettore dati, stesso motore, stesso assemblatore di
`production-planning initial`) ma si ferma PRIMA del commit: nessun run, nessun piano, nessuna allocazione,
nessun consumo di identificativi. Il lettore dati apre una transazione READ ONLY.

Ipotesi di calcolo ("da zero"): le allocazioni attive dei piani vecchi NON trattengono merce, cioe' ogni risorsa
(stock, raccolte, semine in corso) e' disponibile per intero e la domanda aperta viene coperta nell'ordine del
planner (consegna piu' vicina per prima; stock, poi raccolte, poi produzione in corso). Serve a rispondere a
"quanto devo ancora seminare per tornare in pari?". Non e' il piano committato.

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-06_piano_ipotetico.py
  opzione: --business-at 2026-10-06T19:00:00+01:00   (default: adesso, fuso Atlantic/Canary, al minuto)
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

from src.tpo_core.application.production_planning.assembler import ProductionPlanningCommitAssembler  # noqa: E402
from src.tpo_core.application.production_planning.engine import ProductionPlanningEngine  # noqa: E402
from src.tpo_core.application.production_planning.errors import ProductionPlanningError  # noqa: E402
from src.tpo_core.application.production_planning.models import (  # noqa: E402
    ExactQuantity, InitialProductionPlanningCommand, PlanningExecutionContext, PolicyVersionReference,
    ProductionPlanningAssemblyInput, ProductionPlanningRunSnapshot, PublicId,
)
from src.tpo_core.domain.identifiers import ActorId  # noqa: E402
from src.tpo_core.infrastructure.postgresql.production_planning_input import (  # noqa: E402
    PostgreSQLProductionPlanningInputAdapter,
)

ACTOR = "matteo"
REASON = "Piano ipotetico di sola lettura (nessun commit)"
CORRELATION = "piano-ipotetico-sola-lettura"


def default_business_at() -> str:
    return datetime.now(ZoneInfo("Atlantic/Canary")).replace(second=0, microsecond=0).isoformat(timespec="seconds")


def free_all_resources(snapshot):
    """Ipotesi 'da zero': nessuna allocazione trattiene merce (le risorse tornano disponibili per intero)."""
    def freed(item, eligible_name):
        eligible = getattr(item, eligible_name)
        return replace(item, allocated=ExactQuantity(Decimal("0"), eligible.unit), allocable_residual=eligible)
    return replace(
        snapshot,
        stock=tuple(freed(i, "eligible") for i in snapshot.stock),
        harvests=tuple(freed(i, "eligible") for i in snapshot.harvests),
        in_progress=tuple(freed(i, "expected_useful") for i in snapshot.in_progress),
        allocations=(),
    )


def hypothetical_plan(factory, business_at: str):
    """(plan, snapshot) senza scrivere nulla. Solleva ProductionPlanningError se il planner rifiuta i dati."""
    command = InitialProductionPlanningCommand(
        datetime.fromisoformat(business_at), PolicyVersionReference("DEFAULT", 1),
        PlanningExecutionContext(ActorId(ACTOR), REASON, CORRELATION),
    )
    loaded = PostgreSQLProductionPlanningInputAdapter(factory).load(command)
    snapshot = free_all_resources(loaded.snapshot)
    candidates = tuple(ProductionPlanningEngine().calculate(snapshot))
    run = ProductionPlanningRunSnapshot(PublicId("RPP-900000"), 0, "OPEN")
    plan = ProductionPlanningCommitAssembler().plan(
        ProductionPlanningAssemblyInput(command, run, snapshot, candidates, ()))
    return plan, snapshot


def _names(cursor) -> dict[str, str]:
    cursor.execute("SELECT public_id, denominazione FROM tpo.varieta")
    return {r[0]: r[1] for r in cursor.fetchall()}


def report(plan, snapshot, variety_names, business_at, out=print) -> dict[str, Decimal]:
    now = datetime.fromisoformat(business_at)
    out(f"== PIANO IPOTETICO al {business_at} (NULLA E' STATO SCRITTO)")
    out(f"Risorse viste dal planner: stock {len(snapshot.stock)}, raccolte {len(snapshot.harvests)}, "
        f"semine in corso {len(snapshot.in_progress)}; righe di domanda {len(plan.planning_lines)}")
    out("\nordine | riga | varieta | consegna | residuo | da stock | da raccolta | da semine in corso | scoperto | "
        "DA SEMINARE (SET) | semina entro")
    to_sow: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    first: dict[str, datetime] = {}
    for line in sorted(plan.planning_lines, key=lambda l: (l.candidate.demand.delivery_date, l.candidate.demand.order_public_id.value)):
        d = line.candidate.demand
        name = variety_names.get(d.variety_public_id.value, d.variety_public_id.value)
        sow = line.authorized_productive_quantity.value
        sowing_at = line.candidate.sowing_at
        late = " <<< GIA' IN RITARDO" if sow > 0 and sowing_at < now else ""
        out(f"{d.order_public_id.value} | {d.order_line_public_id.value} | {name} | {d.delivery_date} | "
            f"{d.commercial_residual.value} | {line.stock_coverage.value} | {line.allocated_harvest_coverage.value} | "
            f"{line.in_progress_coverage.value} | {line.production_deficit.value} | {sow} | "
            f"{sowing_at:%Y-%m-%d %H:%M}{late}")
        if sow > 0:
            to_sow[name] += sow
            if name not in first or sowing_at < first[name]:
                first[name] = sowing_at
    out("\n== RIEPILOGO PER VARIETA' (SET da seminare per coprire la domanda aperta)")
    out("varieta | SET da seminare | prima semina entro")
    for name in sorted(to_sow):
        out(f"{name} | {to_sow[name]} | {first[name]:%Y-%m-%d %H:%M}")
    if not to_sow:
        out("Niente da seminare: la domanda aperta e' coperta da stock, raccolte e produzione in corso.")
    out("\nLettura: 'DA SEMINARE' include il buffer e l'arrotondamento della policy DEFAULT v1. "
        "Le allocazioni dei piani vecchi sono ignorate (ipotesi da zero). Il piano committato resta quello vecchio.")
    return dict(to_sow)


def run(factory, business_at: str, out=print) -> int:
    try:
        plan, snapshot = hypothetical_plan(factory, business_at)
    except ProductionPlanningError as error:
        out(f"STOP: il planner rifiuta i dati: {error.category} {error.code} - {error.safe_message}")
        return 2
    conn = factory.connect()
    try:
        names = _names(conn.cursor())
    finally:
        conn.close()
    report(plan, snapshot, names, business_at, out)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--business-at", default=None)
    args = ap.parse_args()
    from secret_boundary import load_postgresql_parameters
    from src.tpo_core.infrastructure.postgresql.connection import PostgreSQLConnectionFactory
    from src.tpo_core.infrastructure.postgresql.settings import PostgreSQLSettings
    p = load_postgresql_parameters()
    settings = PostgreSQLSettings.from_mapping({
        "host": p["host"], "port": p["port"], "database": p["dbname"], "user": p["user"],
        "password": p["password"], "sslmode": p["sslmode"], "connect_timeout_seconds": p["connect_timeout"]})
    return run(PostgreSQLConnectionFactory(settings), args.business_at or default_business_at())


if __name__ == "__main__":
    sys.exit(main())
