"""Semine in corso per stadio (16/10/2026), su PostgreSQL usa-e-getta. Sola lettura."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from tests.infrastructure.postgresql.test_chiusura_guidata_script import _connect, _semina
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-16_semine_in_corso.py"


def _module():
    spec = importlib.util.spec_from_file_location("semine_in_corso", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_counts_sets_between_germination_and_growth_and_keeps_the_rest_apart(writer_postgresql_engine):
    e = writer_postgresql_engine
    _semina(e, 973001, "TST-1610-A", raccolto="0.5", atteso="2", stato="GERMINAZIONE")
    _semina(e, 973002, "TST-1610-B", raccolto="0.5", atteso="3", stato="LUCE")
    _semina(e, 973003, "TST-1610-C", raccolto="0.5", atteso="1.5", stato="CRESCITA")
    _semina(e, 973004, "TST-1610-D", raccolto="2", atteso="4", stato="PRONTA_ALLA_RACCOLTA")
    _semina(e, 973005, "TST-1610-E", raccolto="0.5", atteso="1", stato="AVVIATA")
    _semina(e, 973006, "TST-1610-F", raccolto="0.5", atteso=None, stato="CRESCITA")
    conn = _connect(e)
    testo = "\n".join(_module().rapporto(_module().leggi(conn.cursor())))
    conn.close()
    assert "TRA GERMINAZIONE E CRESCITA: 6.5 SET in 4 semine (germinazione 2, luce 3, crescita 1.5)" in testo
    assert "SET ? (resa attesa non compilata, non contata): SEM-973006" in testo
    assert "AVVIATE (appena messe, non ancora in germinazione): 1 SET in 1 semine" in testo
    assert "PRONTE ALLA RACCOLTA (non sommate sopra): 4 SET in 1 semine" in testo
    assert "SEM-973004 TST-1610-D" in testo and "raccolti 2" in testo
