"""Reader BOLLA DI CONSEGNA su PostgreSQL reale (database usa-e-getta).

Le CONSEGNE vengono pubblicate dal writer reale, cosi' i consumi di lotto sono
quelli veri (CONSUMO_LOTTO, migrazione 20261002_0036). Solo la catena
raccolta -> semina viene seminata a mano, con i controlli di chiave esterna
sospesi (session_replication_role=replica) perche' qui interessa la lettura,
non la costruzione dell'intera filiera produttiva.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from src.tpo_core.application.bolla_lettura import (
    BollaLetturaService, ConsegnaNonTrovataError, RichiediBolla,
)
from src.tpo_core.domain.identifiers import ConsegnaId
from src.tpo_core.infrastructure.postgresql.bolla_lettura import PostgreSQLBollaLetturaReader
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    NOW, TZ, _command, _Factory, _seed, _writer,
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)


def _seed_carico_da_raccolta(engine, number: int, quantity: str, codice: str,
                             when: datetime) -> None:
    """Semina SEM/RAC/MOV-CARICO collegati, per la VARIETA VAR-<number>."""
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        variety_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.varieta WHERE public_id=%s", (f"VAR-{number:06d}",),
        ).scalar_one()
        semina_pk = connection.exec_driver_sql("""
          INSERT INTO tpo.semine
            (public_id,varieta_id,cultivar_id,cultivar_uso_id,lotto_seme_id,
             protocollo_versione_id,stato,quantita_seme,unita_misura,data_avvio,
             causa_origine,cultivar_snapshot,uso_produttivo_snapshot,
             lotto_seme_snapshot,protocollo_snapshot,created_by,codice_tracciabilita)
          VALUES (%s,%s,1,1,1,1,'AVVIATA',10,'GRAM',%s,'PIANO_PRODUZIONE',
                  'x','x','x','x','bolla-test',%s) RETURNING id
        """, (f"SEM-{number:06d}", variety_pk, when, codice)).scalar_one()
        raccolta_pk = connection.exec_driver_sql("""
          INSERT INTO tpo.raccolte
            (public_id,semina_id,data_raccolta,quantita,unita_misura,created_by)
          VALUES (%s,%s,%s,%s,'SET','bolla-test') RETURNING id
        """, (f"RAC-{number:06d}", semina_pk, when, quantity)).scalar_one()
        connection.exec_driver_sql("""
          INSERT INTO tpo.movimenti_magazzino
            (public_id,varieta_id,unita_misura,tipo,direzione,quantita,data_movimento,
             motivo,origine_tipo,raccolta_id,created_at,created_by)
          VALUES (%s,%s,'SET','CARICO','POSITIVO',%s,%s,'carico da raccolta','RACCOLTA',
                  %s,%s,'bolla-test')
        """, (f"MOV-{number + 100:06d}", variety_pk, quantity, when, raccolta_pk, NOW))


def _service(engine) -> BollaLetturaService:
    return BollaLetturaService(PostgreSQLBollaLetturaReader(_Factory(engine)))


def test_bolla_reports_lot_code_and_untraced_remainder(writer_postgresql_engine) -> None:
    """Giacenza 2 SET = 1 senza origine + 1 da raccolta tracciata. La consegna
    di 2 SET consuma prima la giacenza senza origine (D5), poi il lotto: la
    bolla deve riportare il codice per 1 SET e 'senza origine' per l'altro."""
    engine = writer_postgresql_engine
    _seed(engine, 930001, stock="2", order_quantity="2")
    _seed_carico_da_raccolta(engine, 930001, "1", "TST-0110-A",
                             datetime(2099, 1, 1, 8, tzinfo=TZ))
    _writer(engine).publish(_command(930001, "2", movement=930001))

    bolla = _service(engine).bolla(RichiediBolla(ConsegnaId("CON-930001")))

    assert bolla.stato == "CONSEGNATA"
    assert bolla.cliente_id == "CLI-930001"
    assert len(bolla.righe) == 1
    riga = bolla.righe[0]
    assert riga.varieta_id == "VAR-930001"
    assert riga.quantita == Decimal("2")
    assert [(o.codice_tracciabilita, o.raccolta_id, o.quantita) for o in riga.origini] == [
        ("TST-0110-A", "RAC-930001", Decimal("1")),
    ]
    assert riga.quantita_senza_origine == Decimal("1")
    assert bolla.righe_senza_origine == 1


def test_bolla_without_lot_ledger_shows_everything_as_untraced(writer_postgresql_engine) -> None:
    """Consegna senza alcun CARICO tracciabile (come le consegne storiche): la
    bolla c'e' e dichiara tutto 'senza origine', senza inventare un codice."""
    engine = writer_postgresql_engine
    _seed(engine, 930002, stock="2")
    _writer(engine).publish(_command(930002, "1", movement=930002))

    bolla = _service(engine).bolla(RichiediBolla(ConsegnaId("CON-930002")))

    riga = bolla.righe[0]
    assert riga.origini == ()
    assert riga.quantita_senza_origine == Decimal("1")


def test_bolla_unknown_consegna_is_reported(writer_postgresql_engine) -> None:
    with pytest.raises(ConsegnaNonTrovataError):
        _service(writer_postgresql_engine).bolla(RichiediBolla(ConsegnaId("CON-999999")))
