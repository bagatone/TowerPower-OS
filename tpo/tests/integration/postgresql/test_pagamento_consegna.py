"""PAGAMENTO CONSEGNA V1 su PostgreSQL reale usa e getta."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
import uuid

from alembic import command as alembic_command
import psycopg
import pytest
import sqlalchemy as sa

from src.tpo_core.application.bolla_lettura.models import RichiediBolla
from src.tpo_core.application.fornitura_ordini_consegne_lettura.models import (
    RichiediElencoConsegne,
)
from src.tpo_core.application.pagamento_consegna.errors import (
    InvalidPagamentoConsegnaCommandError, PagamentoConsegnaGiaAnnullatoError,
    PagamentoConsegnaGiaPagataError, PagamentoConsegnaIdempotencyConflictError,
    PagamentoConsegnaImportoInvalidoError, PagamentoConsegnaNonConsegnataError,
    PagamentoConsegnaNonTrovataError, PagamentoConsegnaOriginaleNonTrovatoError,
)
from src.tpo_core.application.pagamento_consegna.models import (
    AnnullaPagamentoConsegna, PagamentoConsegnaAuthority, RegistraPagamentoConsegna,
)
from src.tpo_core.domain.identifiers import ActorId, ConsegnaId, PagamentoConsegnaId
from src.tpo_core.domain.states import MetodoPagamento
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.bolla_lettura import PostgreSQLBollaLetturaReader
from src.tpo_core.infrastructure.postgresql.fornitura_ordini_consegne_lettura import (
    PostgreSQLFornituraOrdiniConsegneLetturaReader,
)
from src.tpo_core.infrastructure.postgresql.pagamento_consegna import (
    PostgreSQLPagamentoConsegnaWriter,
)
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql,
)


class _Factory:
    def __init__(self, engine) -> None:
        self.url = engine.url

    def connect(self):
        return psycopg.connect(
            host=self.url.host, port=self.url.port, dbname=self.url.database,
            user=self.url.username, connect_timeout=5,
        )


@pytest.fixture
def environment(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_pagcons_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    with engine.begin() as c:
        alembic_command.upgrade(make_config(connection=c), "head")
        c.exec_driver_sql("""
            INSERT INTO tpo.clienti(public_id,denominazione,created_by,updated_at,updated_by)
            VALUES ('CLI-000001','Cliente Test','test',CURRENT_TIMESTAMP,'test')
        """)
        for number, state in ((1, "CONSEGNATA"), (2, "CONSEGNATA"), (3, "PROGRAMMATA")):
            effective = "CURRENT_TIMESTAMP" if state == "CONSEGNATA" else "NULL"
            c.exec_driver_sql(f"""
                INSERT INTO tpo.consegne(public_id,cliente_id,stato,data_prevista,data_effettiva,created_by)
                SELECT 'CON-00000{number}',id,'{state}',DATE '2026-10-09',{effective},'test'
                FROM tpo.clienti WHERE public_id='CLI-000001'
            """)
    factory = _Factory(engine)
    try:
        yield engine, PostgreSQLPagamentoConsegnaWriter(factory), factory
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')


def pay(key="pay-1", *, consegna="CON-000001", data=date(2026, 10, 9),
        metodo=MetodoPagamento.CONTANTI, importo=None, note=None, storico=False):
    return RegistraPagamentoConsegna(
        ConsegnaId(consegna), data, metodo,
        PagamentoConsegnaAuthority(ActorId("owner"), "pagamento ricevuto", f"corr-{key}", key),
        importo, note, storico,
    )


def undo(key="undo-1", *, original="PGC-000001", note=None):
    return AnnullaPagamentoConsegna(
        PagamentoConsegnaId(original),
        PagamentoConsegnaAuthority(ActorId("owner"), "registrato per errore", f"corr-{key}", key),
        note,
    )


def scalar(engine, sql):
    with engine.connect() as connection:
        return connection.exec_driver_sql(sql).scalar_one()


def test_register_with_and_without_amount_replay_conflict_and_audit(environment):
    engine, writer, _ = environment
    first = writer.record(pay())
    assert first.pagamento_id.value == "PGC-000001" and first.importo is None
    replay = writer.record(pay())
    assert replay.outcome == "COMPATIBLE_REPLAY" and replay.pagamento_id == first.pagamento_id
    with pytest.raises(PagamentoConsegnaIdempotencyConflictError):
        writer.record(pay(importo=Decimal("12.50")))
    second = writer.record(pay("pay-2", consegna="CON-000002", importo=Decimal("12.50"),
                               metodo=MetodoPagamento.BIZUM, note="in negozio"))
    assert second.pagamento_id.value == "PGC-000002" and second.importo == Decimal("12.50")
    assert scalar(engine, "SELECT count(*) FROM tpo.pagamenti_consegna") == 2
    assert scalar(engine, "SELECT count(*) FROM tpo.audit_eventi "
                          "WHERE entity_type='PAGAMENTO_CONSEGNA' AND operation='INSERT'") == 2
    assert scalar(engine, "SELECT next_value FROM tpo.id_sequences "
                          "WHERE sequence_name='PAGAMENTO_CONSEGNA_ID'") == 3


def test_second_payment_rejected_until_first_is_cancelled(environment):
    engine, writer, _ = environment
    writer.record(pay())
    with pytest.raises(PagamentoConsegnaGiaPagataError, match="PGC-000001"):
        writer.record(pay("pay-again"))
    cancelled = writer.cancel(undo())
    assert cancelled.annullamento_id.value == "PGC-000002"
    assert cancelled.pagamento_id.value == "PGC-000001" and cancelled.consegna_id.value == "CON-000001"
    # annullato: si puo' registrare quello giusto
    again = writer.record(pay("pay-right", metodo=MetodoPagamento.BONIFICO))
    assert again.pagamento_id.value == "PGC-000003"
    assert scalar(engine, "SELECT count(*) FROM tpo.audit_eventi "
                          "WHERE entity_type='PAGAMENTO_CONSEGNA' AND operation='CORRECTION'") == 1


def test_cancel_rules(environment):
    engine, writer, _ = environment
    with pytest.raises(PagamentoConsegnaOriginaleNonTrovatoError):
        writer.cancel(undo(original="PGC-000009"))
    writer.record(pay())
    first = writer.cancel(undo())
    replay = writer.cancel(undo())
    assert replay.outcome == "COMPATIBLE_REPLAY" and replay.annullamento_id == first.annullamento_id
    with pytest.raises(PagamentoConsegnaGiaAnnullatoError):
        writer.cancel(undo("undo-2"))
    # un annullamento non si annulla e non e' un pagamento
    with pytest.raises(PagamentoConsegnaOriginaleNonTrovatoError):
        writer.cancel(undo("undo-3", original="PGC-000002"))
    with pytest.raises(PagamentoConsegnaIdempotencyConflictError):
        writer.cancel(undo(note="altro"))
    # stessa chiave usata per un'altra operazione = conflitto, non replay
    with pytest.raises(PagamentoConsegnaIdempotencyConflictError):
        writer.record(pay("undo-1"))


def test_only_delivered_existing_consegne(environment):
    engine, writer, _ = environment
    with pytest.raises(PagamentoConsegnaNonTrovataError):
        writer.record(pay(consegna="CON-000099"))
    with pytest.raises(PagamentoConsegnaNonConsegnataError):
        writer.record(pay(consegna="CON-000003"))
    assert scalar(engine, "SELECT count(*) FROM tpo.pagamenti_consegna") == 0
    assert scalar(engine, "SELECT next_value FROM tpo.id_sequences "
                          "WHERE sequence_name='PAGAMENTO_CONSEGNA_ID'") == 1


def test_concurrent_identical_requests_and_distinct_consegne(environment):
    engine, writer, _ = environment
    with ThreadPoolExecutor(max_workers=2) as pool:
        same = list(pool.map(lambda _: writer.record(pay("same")), range(2)))
    assert {r.pagamento_id.value for r in same} == {"PGC-000001"}
    assert {r.outcome for r in same} == {"INSERTED", "COMPATIBLE_REPLAY"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        # due richieste diverse sulla stessa consegna gia' pagata: nessuna passa
        results = []
        for future in [pool.submit(writer.record, pay(f"k{i}")) for i in range(2)]:
            try:
                results.append(future.result())
            except PagamentoConsegnaGiaPagataError:
                results.append("rifiutata")
    assert results == ["rifiutata", "rifiutata"]
    assert scalar(engine, "SELECT count(*) FROM tpo.pagamenti_consegna") == 1


def test_command_validation():
    with pytest.raises(PagamentoConsegnaImportoInvalidoError):
        pay(importo=Decimal("0"))
    with pytest.raises(PagamentoConsegnaImportoInvalidoError):
        pay(importo=Decimal("1.234"))
    with pytest.raises(PagamentoConsegnaImportoInvalidoError):
        pay(importo=12.5)
    with pytest.raises(InvalidPagamentoConsegnaCommandError):
        pay(note=" spazi ")
    with pytest.raises(InvalidPagamentoConsegnaCommandError):
        RegistraPagamentoConsegna(
            ConsegnaId("CON-000001"), date(2026, 10, 9), "NON-UN-METODO",
            PagamentoConsegnaAuthority(ActorId("o"), "r", "c", "k"),
        )


def test_database_immutability_and_shape(environment):
    engine, writer, _ = environment
    writer.record(pay())
    for statement in (
        "UPDATE tpo.pagamenti_consegna SET metodo='CARTA' WHERE public_id='PGC-000001'",
        "DELETE FROM tpo.pagamenti_consegna WHERE public_id='PGC-000001'",
    ):
        with pytest.raises(sa.exc.DBAPIError, match="immutable"):
            with engine.begin() as connection:
                connection.exec_driver_sql(statement)
    # due pagamenti attivi sulla stessa consegna: rifiutati dal database stesso
    with pytest.raises(sa.exc.DBAPIError, match="gia' pagata"):
        with engine.begin() as connection:
            connection.exec_driver_sql("""
                INSERT INTO tpo.pagamenti_consegna
                  (public_id,consegna_id,tipo,data_pagamento,metodo,idempotency_key,payload_hash,
                   reason,correlation_id,created_by)
                SELECT 'PGC-000777',consegna_id,'PAGAMENTO',DATE '2026-10-09','CARTA','x','h','r','c','t'
                FROM tpo.pagamenti_consegna WHERE public_id='PGC-000001'
            """)
    # un PAGAMENTO senza data e' una forma non valida
    with pytest.raises(sa.exc.DBAPIError):
        with engine.begin() as connection:
            connection.exec_driver_sql("""
                INSERT INTO tpo.pagamenti_consegna
                  (public_id,consegna_id,tipo,metodo,idempotency_key,payload_hash,reason,
                   correlation_id,created_by)
                SELECT 'PGC-000778',id,'PAGAMENTO','CARTA','y','h','r','c','t'
                FROM tpo.consegne WHERE public_id='CON-000002'
            """)


def test_readers_show_paid_unpaid_and_storico(environment):
    engine, writer, factory = environment
    bolla_reader = PostgreSQLBollaLetturaReader(factory)
    consegne_reader = PostgreSQLFornituraOrdiniConsegneLetturaReader(factory)

    def stato():
        elenco = consegne_reader.consegne(RichiediElencoConsegne())
        return {c.consegna_id.value: c.stato_pagamento for c in elenco.consegne}

    assert stato() == {"CON-000001": "DA_PAGARE", "CON-000002": "DA_PAGARE",
                       "CON-000003": "NON_CONSEGNATA"}
    assert bolla_reader.bolla(RichiediBolla(ConsegnaId("CON-000001"))).pagamento is None

    writer.record(pay(importo=Decimal("12.50"), metodo=MetodoPagamento.BIZUM))
    writer.record(pay("old", consegna="CON-000002", metodo=MetodoPagamento.ALTRO, storico=True,
                      data=date(2026, 10, 11)))
    assert stato() == {"CON-000001": "PAGATA", "CON-000002": "PAGATA",
                       "CON-000003": "NON_CONSEGNATA"}
    b1 = bolla_reader.bolla(RichiediBolla(ConsegnaId("CON-000001"))).pagamento
    assert (b1.metodo, b1.importo, b1.storico) == ("BIZUM", Decimal("12.50"), False)
    b2 = bolla_reader.bolla(RichiediBolla(ConsegnaId("CON-000002"))).pagamento
    assert b2.storico is True and b2.importo is None

    writer.cancel(undo())
    assert stato()["CON-000001"] == "DA_PAGARE"
    assert bolla_reader.bolla(RichiediBolla(ConsegnaId("CON-000001"))).pagamento is None
