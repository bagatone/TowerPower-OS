from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
import sqlalchemy as sa

from src.tpo_core.infrastructure.postgresql.alembic import make_config
from tests.infrastructure.postgresql.test_production_planning_migrations import isolated_postgresql
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _seed_authorities


ROOT = Path(__file__).parents[3]
SOURCE_PATH = ROOT / "migrations/versions/20260903_0027_raccolta_correzione_authority.py"
BASE = datetime(2026, 8, 30, 8, tzinfo=timezone.utc)


def test_raccolta_correzione_migration_is_linear_head():
    config = Config(str(ROOT / "migrations/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["20260905_0030"]
    revision = script.get_revision("20260903_0027")
    assert revision.down_revision == "20260903_0026"


def test_raccolta_correzione_migration_uses_established_offline_mode_precedent():
    source = SOURCE_PATH.read_text()
    assert "from alembic import context, op" in source
    assert "context.is_offline_mode()" in source
    assert "op.get_context().as_sql" not in source


def test_raccolta_correzione_migration_contains_frozen_guards():
    source = SOURCE_PATH.read_text()
    for fragment in (
        "rettifica_raccolta_id", "fk_raccolte_rettifica",
        "ck_raccolte_ordinary_or_correction", "raccolta_correzione_requests",
        "uq_raccolta_correzione_request_key", "fn_raccolte_rettifica_coerente",
        "fn_check_raccolta_net_quantity", "ct_raccolte_net_quantity_nonnegative",
        "protect_raccolta_correzione_request",
        "cannot downgrade: governed RACCOLTA CORREZIONE authority history exists",
    ):
        assert fragment in source


def test_raccolta_correzione_migration_has_no_business_dml():
    source = SOURCE_PATH.read_text()
    for statement in ("INSERT INTO", "UPDATE tpo.", "DELETE FROM"):
        assert statement not in source
    assert "id_sequences" not in source


# --- Constraint / trigger behaviour on a real, migrated PostgreSQL ---------------

@pytest.fixture(scope="module")
def correzione_engine(isolated_postgresql):
    """Materialize the migration once and seed two eligible SEMINE for the module."""
    connection = isolated_postgresql
    config = make_config(connection=connection)
    alembic_command.upgrade(config, "head")
    _seed_authorities(connection)
    connection.exec_driver_sql(
        "UPDATE tpo.varieta SET codice_tracciabilita='AFI' WHERE public_id='VAR-000001'"
    )
    connection.exec_driver_sql("""
        INSERT INTO tpo.sementi
          (fornitore,referenza_commerciale,attiva,created_by,updated_at,updated_by,version)
        VALUES ('Supplier','REF',true,'test',CURRENT_TIMESTAMP,'test',0);
        INSERT INTO tpo.semente_impieghi
          (semente_id,cultivar_uso_id,raccomandazione,ultima_revisione,
           created_by,updated_at,updated_by,version)
        SELECT s.id,cu.id,'RACCOMANDATA',DATE '2026-08-25','test',
               CURRENT_TIMESTAMP,'test',0
        FROM tpo.sementi s CROSS JOIN tpo.cultivar_usi cu
        WHERE s.fornitore='Supplier';
        INSERT INTO tpo.lotti_seme
          (public_id,semente_id,numero_lotto_produttore,data_ricezione,
           quantita_iniziale,quantita_residua,unita_misura,
           created_by,updated_at,updated_by,version)
        SELECT 'LSE-000001',id,'LOT-1',DATE '2026-08-24',10,10,'GRAM',
               'test',CURRENT_TIMESTAMP,'test',0
        FROM tpo.sementi WHERE fornitore='Supplier';
    """)
    for public_id, discriminator in (("SEM-000001", "A"), ("SEM-000002", "B")):
        connection.exec_driver_sql(
            """
            INSERT INTO tpo.semine
              (public_id,varieta_id,cultivar_id,cultivar_uso_id,lotto_seme_id,
               protocollo_versione_id,stato,quantita_seme,unita_misura,
               data_avvio,causa_origine,cultivar_snapshot,
               uso_produttivo_snapshot,lotto_seme_snapshot,protocollo_snapshot,
               created_by,codice_tracciabilita)
            SELECT %s,v.id,c.id,cu.id,l.id,pv.id,
                   'PRONTA_ALLA_RACCOLTA',1,'GRAM',
                   TIMESTAMPTZ '2026-08-25 08:00:00+00','ORDINE_CLIENTE',
                   'Afila','Microgreen','LOT-1','PV-000001','test',%s
            FROM tpo.varieta v
            JOIN tpo.cultivar c ON c.varieta_id=v.id
            JOIN tpo.cultivar_usi cu ON cu.cultivar_id=c.id
            CROSS JOIN tpo.lotti_seme l
            CROSS JOIN tpo.protocollo_versioni pv
            WHERE v.public_id='VAR-000001' AND l.public_id='LSE-000001'
              AND pv.public_id='PV-000001'
            """,
            (public_id, f"AFI-2508-{discriminator}"),
        )
    connection.commit()
    return connection


def _semina_pk(connection, public_id: str) -> int:
    return connection.exec_driver_sql(
        "SELECT id FROM tpo.semine WHERE public_id=%s", (public_id,)
    ).scalar_one()


def _insert_raccolta(connection, public_id, semina_public_id, quantita, *,
                      rettifica_di=None, at=BASE, unita_misura="SET"):
    semina_pk = _semina_pk(connection, semina_public_id)
    rettifica_pk = None
    if rettifica_di is not None:
        rettifica_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.raccolte WHERE public_id=%s", (rettifica_di,)
        ).scalar_one()
    return connection.exec_driver_sql(
        """INSERT INTO tpo.raccolte
           (public_id,semina_id,data_raccolta,quantita,unita_misura,
            rettifica_raccolta_id,created_by)
           VALUES (%s,%s,%s,%s,%s,%s,'test') RETURNING id""",
        (public_id, semina_pk, at, quantita, unita_misura, rettifica_pk),
    ).scalar_one()


def _self_reference_insert(connection, public_id, semina_public_id, at=BASE):
    semina_pk = _semina_pk(connection, semina_public_id)
    connection.exec_driver_sql(
        """
        WITH next_id AS (
          SELECT nextval(pg_get_serial_sequence('tpo.raccolte', 'id')) AS id
        )
        INSERT INTO tpo.raccolte
          (id,public_id,semina_id,data_raccolta,quantita,unita_misura,
           rettifica_raccolta_id,created_by)
        SELECT next_id.id,%s,%s,%s,-0.1,'SET',next_id.id,'test'
        FROM next_id
        """,
        (public_id, semina_pk, at),
    )


def _force_constraints(connection) -> None:
    connection.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")


def _assert_connection_healthy(connection) -> None:
    assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1


def _expect_db_failure(connection, marker: str, action) -> None:
    savepoint = connection.begin_nested()
    try:
        with pytest.raises(sa.exc.DBAPIError, match=marker):
            action()
            _force_constraints(connection)
    finally:
        savepoint.rollback()
    _assert_connection_healthy(connection)


def test_ordinary_row_still_requires_positive_quantity(correzione_engine):
    connection = correzione_engine
    _expect_db_failure(
        connection, "ck_raccolte_ordinary_or_correction",
        lambda: _insert_raccolta(connection, "RAC-800001", "SEM-000001", "0"),
    )


def test_correction_row_rejects_zero_quantity(correzione_engine):
    connection = correzione_engine
    _insert_raccolta(connection, "RAC-800002", "SEM-000001", "1")
    connection.commit()
    _expect_db_failure(
        connection, "ck_raccolte_ordinary_or_correction",
        lambda: _insert_raccolta(
            connection, "RAC-800003", "SEM-000001", "0", rettifica_di="RAC-800002",
        ),
    )


def test_self_reference_is_rejected(correzione_engine):
    connection = correzione_engine
    _expect_db_failure(
        connection, "self reference",
        lambda: _self_reference_insert(connection, "RAC-800010", "SEM-000001"),
    )


def test_chained_correction_is_rejected(correzione_engine):
    connection = correzione_engine
    _insert_raccolta(connection, "RAC-800020", "SEM-000001", "1")
    _insert_raccolta(
        connection, "RAC-800021", "SEM-000001", "-0.5", rettifica_di="RAC-800020",
    )
    connection.commit()
    _expect_db_failure(
        connection, "ct_raccolte_rettifica_coerente",
        lambda: _insert_raccolta(
            connection, "RAC-800022", "SEM-000001", "-0.25", rettifica_di="RAC-800021",
        ),
    )


def test_cross_semina_correction_is_rejected(correzione_engine):
    connection = correzione_engine
    _insert_raccolta(connection, "RAC-800030", "SEM-000001", "1")
    connection.commit()
    _expect_db_failure(
        connection, "ct_raccolte_rettifica_coerente",
        lambda: _insert_raccolta(
            connection, "RAC-800031", "SEM-000002", "-0.5", rettifica_di="RAC-800030",
        ),
    )


def test_net_quantity_cannot_go_negative(correzione_engine):
    connection = correzione_engine
    _insert_raccolta(connection, "RAC-800040", "SEM-000001", "1")
    connection.commit()
    _expect_db_failure(
        connection, "ct_raccolte_net_quantity_nonnegative",
        lambda: _insert_raccolta(
            connection, "RAC-800041", "SEM-000001", "-1.5", rettifica_di="RAC-800040",
        ),
    )


def test_net_quantity_can_reach_exactly_zero_and_further_correction_then_fails(correzione_engine):
    connection = correzione_engine
    _insert_raccolta(connection, "RAC-800050", "SEM-000001", "1")
    _insert_raccolta(
        connection, "RAC-800051", "SEM-000001", "-1",
        rettifica_di="RAC-800050", at=BASE + timedelta(minutes=1),
    )
    connection.commit()
    net = connection.exec_driver_sql(
        """SELECT r.quantita + COALESCE(
                    (SELECT sum(c.quantita) FROM tpo.raccolte c
                     WHERE c.rettifica_raccolta_id = r.id), 0)
           FROM tpo.raccolte r WHERE r.public_id='RAC-800050'"""
    ).scalar_one()
    assert net == 0
    _expect_db_failure(
        connection, "ct_raccolte_net_quantity_nonnegative",
        lambda: _insert_raccolta(
            connection, "RAC-800052", "SEM-000001", "-0.0000010",
            rettifica_di="RAC-800050", at=BASE + timedelta(minutes=2),
        ),
    )


def test_correction_row_is_still_covered_by_database_immutability(correzione_engine):
    connection = correzione_engine
    _insert_raccolta(connection, "RAC-800060", "SEM-000001", "1")
    _insert_raccolta(
        connection, "RAC-800061", "SEM-000001", "-0.5", rettifica_di="RAC-800060",
    )
    connection.commit()
    for statement in (
        "UPDATE tpo.raccolte SET quantita=-1 WHERE public_id='RAC-800061'",
        "DELETE FROM tpo.raccolte WHERE public_id='RAC-800061'",
    ):
        _expect_db_failure(
            connection, "Raccolta physical fact authority is immutable",
            lambda statement=statement: connection.exec_driver_sql(statement),
        )


# --- Downgrade guard: run in dedicated ephemeral databases to stay independent
# from the committed setup rows created by the constraint tests above. -----------

def _fresh_database(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_raccolta_correzione_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    return name, cluster, engine


def test_real_postgresql_downgrade_blocked_once_a_correction_exists(isolated_postgresql):
    name, cluster, engine = _fresh_database(isolated_postgresql)
    try:
        with engine.begin() as connection:
            config = make_config(connection=connection)
            alembic_command.upgrade(config, "head")
        with engine.connect() as connection:
            config = make_config(connection=connection)
            connection.exec_driver_sql(
                """INSERT INTO tpo.raccolta_correzione_requests
                   (operation_scope,idempotency_key,canonical_payload_hash,raccolta_id,
                    result_public_id,outcome,recorded_at,created_by)
                   VALUES ('RACCOLTA_CORREZIONE_V1','downgrade-guard',%s,NULL,NULL,
                           'RESERVED',CURRENT_TIMESTAMP,'test')""",
                ("a" * 64,),
            )
            with pytest.raises(
                Exception, match="governed RACCOLTA CORREZIONE authority history exists"
            ):
                alembic_command.downgrade(config, "20260903_0026")
            connection.rollback()
            assert connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one() == "20260905_0030"
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')


def test_real_postgresql_downgrade_succeeds_when_untouched(isolated_postgresql):
    name, cluster, engine = _fresh_database(isolated_postgresql)
    try:
        with engine.begin() as connection:
            config = make_config(connection=connection)
            alembic_command.upgrade(config, "head")
        with engine.begin() as connection:
            config = make_config(connection=connection)
            alembic_command.downgrade(config, "20260903_0026")
            assert not sa.inspect(connection).has_table(
                "raccolta_correzione_requests", schema="tpo"
            )
            columns = {
                row[0] for row in connection.exec_driver_sql(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='tpo' AND table_name='raccolte'"
                ).all()
            }
            assert "rettifica_raccolta_id" not in columns
            checks = {
                row[0]: row[1] for row in connection.exec_driver_sql(
                    "SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid='tpo.raccolte'::regclass AND contype='c'"
                ).all()
            }
            # PostgreSQL normalizes the check-constraint definition it stores
            # (adds parens and an explicit numeric cast); assert against that
            # canonical form rather than the literal DDL text we authored.
            assert "quantita > (0)::numeric" in checks["ck_raccolte_quantita_positive"]
            alembic_command.upgrade(config, "head")
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
