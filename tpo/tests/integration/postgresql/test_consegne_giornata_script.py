"""Consegne dell'8/10/2026: controlli e anteprima della fase 'pronta' su PostgreSQL reale usa-e-getta.

I comandi di scrittura passano dal CLI (`tpo ...`), gia' coperti dai loro test; qui si verificano le
protezioni dello script (semina/varieta'/SET dichiarati, stato di partenza) e che l'anteprima non scriva."""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest

from src.tpo_core.application.semina_commissioning.models import SeminaFactSource
from src.tpo_core.application.semina_lifecycle.models import SeminaLifecycleAuthority, TransitionSemina
from src.tpo_core.domain.identifiers import ActorId, SeminaId
from src.tpo_core.domain.states import SeminaState
from src.tpo_core.infrastructure.postgresql.semina_lifecycle import PostgreSQLSeminaLifecycleWriter
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_production_planning_migrations import isolated_postgresql  # noqa: F401
from tests.integration.postgresql.test_raccolta import BASE, harvest_environment, scalar  # noqa: F401
from tests.integration.postgresql.test_raccolta import environment  # noqa: F401

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-08_consegne_giornata.py"
VARIETY = "Writer test variety"


def _module():
    spec = importlib.util.spec_from_file_location("consegne_giornata", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username, autocommit=True)


def _to_luce(engine):
    writer = PostgreSQLSeminaLifecycleWriter(_Factory(engine))
    for version, state in enumerate([SeminaState.GERMINAZIONE, SeminaState.LUCE]):
        facts = tuple((name, SeminaFactSource.OWNER_AUTHORIZED) for name in ("target_state", "effective_at"))
        writer.transition(TransitionSemina(
            SeminaId("SEM-000001"), version, state, BASE - timedelta(hours=4 - version), None, facts,
            SeminaLifecycleAuthority(ActorId("owner"), "physical transition", f"luce-{version}", f"luce-{version}")))


def _events(engine):
    return scalar(engine, "SELECT count(*) FROM tpo.semina_lifecycle_eventi")


def test_pronta_preview_guards_and_writes_nothing(harvest_environment, capsys):
    engine, _ = harvest_environment
    module = _module()
    when = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)

    with engine.begin() as connection:                       # SET attesi dichiarati dal titolare = 3
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        connection.exec_driver_sql(
            "UPDATE tpo.semine SET expected_useful_quantity=3, expected_useful_uom='SET', "
            "harvest_window_start=data_avvio + interval '9 days', harvest_window_end=data_avvio + interval '14 days'")

    conn = _connect(engine)
    ctx = module.Ctx(False, Path("/tmp/bolle-test"), conn=conn)
    ctx.check_head = lambda: None                            # head alembic del DB di prova != produzione

    module.PRONTA = [("SEM-000001", VARIETY, "3")]
    module.GIA_PRONTE = []
    with pytest.raises(module.Stop, match="parte da LUCE o CRESCITA"):   # AVVIATA: stato non ammesso
        module.fase_pronta(ctx, when)

    _to_luce(engine)
    before = _events(engine)
    module.fase_pronta(ctx, when + timedelta(days=400))
    shown = capsys.readouterr().out
    assert "SEM-000001 -> CRESCITA" in shown and "SEM-000001 -> PRONTA_ALLA_RACCOLTA" in shown
    assert "(anteprima: non eseguito)" in shown and _events(engine) == before

    module.PRONTA = [("SEM-000001", VARIETY, "4")]           # SET dichiarati diversi dagli attesi: non scelgo io
    with pytest.raises(module.Stop, match="non coincidono"):
        module.fase_pronta(ctx, when + timedelta(days=400))
    module.PRONTA = [("SEM-000001", "Altra varieta", "3")]    # varieta' sbagliata per quella semina
    with pytest.raises(module.Stop, match="non Altra varieta"):
        module.fase_pronta(ctx, when + timedelta(days=400))
    module.PRONTA = [("SEM-000001", VARIETY, "3")]            # istante non successivo all'ultimo evento
    with pytest.raises(module.Stop, match="non e' dopo l'ultimo evento"):
        module.fase_pronta(ctx, BASE - timedelta(days=10))
    conn.close()
    assert _events(engine) == before
