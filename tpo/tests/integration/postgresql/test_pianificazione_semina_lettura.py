"""Integration test del reader "Da seminare" (pianificazione_semina_lettura).

Riusa la stessa infrastruttura di test del Commit Writer di Production
Planning (writer_database, _commit, _Factory) invece di costruire a mano
righe tpo.righe_piano_semina: la tabella ha decine di CHECK constraint
derivati (coperture, buffer, timeline) che solo il Writer reale sa
rispettare -- lo stesso principio di riuso gia' applicato altrove nel
progetto (vedi tests/integration/postgresql/test_clienti_lettura.py che
riusa _Factory dallo stesso modulo)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from src.tpo_core.application.pianificazione_semina_lettura.models import (
    RichiediElencoDaSeminare,
)
from src.tpo_core.domain.identifiers import ClienteId, RigaPianoSeminaId, VarietaId
from src.tpo_core.infrastructure.postgresql.pianificazione_semina_lettura import (
    PostgreSQLPianificazioneSeminaLetturaReader,
)
from tests.infrastructure.postgresql.test_production_planning_commit_writer import (
    _commit,
    _Factory,
    writer_cluster,  # noqa: F401 -- fixture dependency required by writer_database
    writer_database,
)
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql as migration_postgresql,  # noqa: F401 -- fixture dependency of writer_cluster
)


def test_elenco_include_riga_pianificata_dopo_commit_iniziale(writer_database):
    _commit(writer_database)
    reader = PostgreSQLPianificazioneSeminaLetturaReader(_Factory(writer_database))

    result = reader.elenco(RichiediElencoDaSeminare())

    assert len(result.righe) == 1
    riga = result.righe[0]
    assert riga.riga_id == RigaPianoSeminaId("RPS-000001")
    assert riga.varieta_id == VarietaId("VAR-000001")
    assert riga.varieta_denominazione == "Writer test variety"
    assert riga.cliente_id == ClienteId("CLI-000001")
    assert riga.cliente_denominazione == "Writer test client"
    assert riga.stato == "PIANIFICATA"
    assert riga.quantita_da_seminare == Decimal("1")
    assert riga.unita_misura == "SET"
    assert riga.grammi_seme_richiesti == Decimal("25")
    assert riga.data_consegna == date(2026, 8, 15)
    assert riga.sowing_at == datetime(2026, 8, 4, 6, 0, tzinfo=timezone.utc)


def test_elenco_e_vuoto_senza_alcun_piano_committato(writer_database):
    reader = PostgreSQLPianificazioneSeminaLetturaReader(_Factory(writer_database))

    result = reader.elenco(RichiediElencoDaSeminare())

    assert result.righe == ()
