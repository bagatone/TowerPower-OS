from datetime import date
from decimal import Decimal
import uuid

from alembic import command as alembic_command
import pytest
import sqlalchemy as sa

from src.tpo_core.application.finanze_lettura.models import (
    RichiediElencoFatture, RichiediElencoIncassi, RichiediElencoUscite,
)
from src.tpo_core.application.incasso.models import IncassoAuthority, RegistraIncasso
from src.tpo_core.application.uscita.models import RegistraUscita, UscitaAuthority
from src.tpo_core.domain.identifiers import ActorId
from src.tpo_core.domain.states import CategoriaUscita, MetodoPagamento
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.finanze_lettura import (
    PostgreSQLFinanzeLetturaReader,
)
from src.tpo_core.infrastructure.postgresql.incasso import PostgreSQLIncassoWriter
from src.tpo_core.infrastructure.postgresql.uscita import PostgreSQLUscitaWriter
from tests.infrastructure.postgresql.test_fattura_emissione_writer import (
    _command as fattura_command, _seed as seed_fattura, _writer as fattura_writer,
    fattura_postgresql_cluster_engine, fattura_postgresql_engine,
)
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql as migration_postgresql,
)


def test_fatture_reads_row_with_righe_e_consegne_collegate(fattura_postgresql_engine):
    engine = fattura_postgresql_engine
    seed_fattura(engine, 940001, consegne=2)
    result = fattura_writer(engine).emit(fattura_command(940001, consegne=2))
    reader = PostgreSQLFinanzeLetturaReader(_Factory(engine))
    elenco = reader.fatture(RichiediElencoFatture())
    assert len(elenco.fatture) == 1
    fattura = elenco.fatture[0]
    assert fattura.numero_fattura == result.numero_fattura
    assert fattura.cliente_id.value == "CLI-940001"
    assert fattura.totale_netto == Decimal("20.00")
    assert fattura.totale_igic == Decimal("1.40")
    assert fattura.totale == Decimal("21.40")
    assert fattura.rettifica_di is None
    assert len(fattura.consegne_collegate) == 2
    assert {c.value for c in fattura.consegne_collegate} == {"CON-940001", "CON-940002"}
    assert len(fattura.righe) == 2
    riga = fattura.righe[0]
    assert riga.varieta_id.value == "VAR-940001"
    assert riga.prezzo_unitario == Decimal("5.0000")
    assert riga.aliquota_igic == Decimal("7.00")


def test_incassi_and_uscite_are_read_alongside_fatture(fattura_postgresql_engine):
    engine = fattura_postgresql_engine
    seed_fattura(engine, 940101)
    emitted = fattura_writer(engine).emit(fattura_command(940101))
    incasso_writer = PostgreSQLIncassoWriter(_Factory(engine))
    incasso_writer.record(RegistraIncasso(
        emitted.numero_fattura, Decimal("21.40"), date(2026, 9, 10), MetodoPagamento.BONIFICO,
        IncassoAuthority(ActorId("owner"), "payment received", "corr-lettura-1", "lettura-1"),
        None,
    ))
    uscita_writer = PostgreSQLUscitaWriter(_Factory(engine))
    uscita_writer.record(RegistraUscita(
        Decimal("45.50"), date(2026, 9, 9), CategoriaUscita.SEMENTI, "Vivai Canarias SL",
        MetodoPagamento.BONIFICO,
        UscitaAuthority(ActorId("owner"), "expense paid", "corr-lettura-2", "lettura-2"), None,
    ))
    reader = PostgreSQLFinanzeLetturaReader(_Factory(engine))
    incassi = reader.incassi(RichiediElencoIncassi())
    assert len(incassi.incassi) == 1
    incasso = incassi.incassi[0]
    assert incasso.fattura_numero == emitted.numero_fattura
    assert incasso.importo == Decimal("21.40")
    assert incasso.metodo == "BONIFICO"
    assert incasso.rettifica_incasso_id is None
    uscite = reader.uscite(RichiediElencoUscite())
    assert len(uscite.uscite) == 1
    uscita = uscite.uscite[0]
    assert uscita.categoria == "SEMENTI"
    assert uscita.beneficiario == "Vivai Canarias SL"
    assert uscita.importo == Decimal("45.50")
    assert uscita.rettifica_uscita_id is None


def test_elenco_empty_when_no_rows(fattura_postgresql_cluster_engine):
    admin_engine = fattura_postgresql_cluster_engine
    name = f"tpo_finanze_lettura_empty_{uuid.uuid4().hex}"
    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(admin_engine.url.set(database=name))
    with engine.begin() as connection:
        alembic_command.upgrade(make_config(connection=connection), "head")
    reader = PostgreSQLFinanzeLetturaReader(_Factory(engine))
    assert reader.fatture(RichiediElencoFatture()).fatture == ()
    assert reader.incassi(RichiediElencoIncassi()).incassi == ()
    assert reader.uscite(RichiediElencoUscite()).uscite == ()
