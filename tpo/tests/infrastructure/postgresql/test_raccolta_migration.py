from pathlib import Path
import uuid

from alembic.config import Config
from alembic import command as alembic_command
from alembic.script import ScriptDirectory
import pytest
import sqlalchemy as sa

from src.tpo_core.infrastructure.postgresql.alembic import make_config
from tests.infrastructure.postgresql.test_production_planning_migrations import isolated_postgresql
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _seed_authorities


ROOT = Path(__file__).parents[3]


def test_raccolta_migration_is_linear_head():
    config = Config(str(ROOT / "migrations/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["20260903_0026"]
    revision = script.get_revision("20260830_0022")
    assert revision.down_revision == "20260826_0021"


def test_raccolta_migration_contains_frozen_guards():
    source = (
        ROOT / "migrations/versions/20260830_0022_raccolta_authority.py"
    ).read_text()
    for authority in (
        "RACCOLTA_ID", "RaccoltaId", "raccolta_recording_requests",
        "uq_raccolta_recording_request_key", "protect_raccolta_authority",
        "protect_raccolta_recording_request", "existing RACCOLTE require reconciliation",
        "cannot downgrade: governed RACCOLTA authority history exists",
    ):
        assert authority in source


def test_real_postgresql_catalog_and_downgrade_fail_closed(isolated_postgresql):
    connection = isolated_postgresql
    config = make_config(connection=connection)
    alembic_command.upgrade(config, "head")
    assert connection.exec_driver_sql(
        "SELECT sequence_name,identifier_type,prefix,next_value FROM tpo.id_sequences "
        "WHERE sequence_name='RACCOLTA_ID'"
    ).one() == ("RACCOLTA_ID", "RaccoltaId", "RAC", 1)
    assert sa.inspect(connection).has_table("raccolta_recording_requests", schema="tpo")
    connection.exec_driver_sql(
        """INSERT INTO tpo.raccolta_recording_requests
           (operation_scope,idempotency_key,canonical_payload_hash,raccolta_id,
            result_public_id,outcome,recorded_at,created_by)
           VALUES ('RACCOLTA_RECORDING_V1','downgrade-guard',%s,NULL,NULL,
                   'RESERVED',CURRENT_TIMESTAMP,'test')""",
        ("a" * 64,),
    )
    with pytest.raises(Exception, match="governed RACCOLTA authority history exists"):
        alembic_command.downgrade(config, "20260826_0021")
    connection.rollback()


def test_forward_cutover_rejects_existing_raccolta_without_mutation(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_raccolta_cutover_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    try:
        with engine.begin() as connection:
            config = make_config(connection=connection)
            alembic_command.upgrade(config, "20260826_0021")
            _seed_authorities(connection)
            connection.exec_driver_sql(
                "UPDATE tpo.varieta SET codice_tracciabilita='AFI' "
                "WHERE public_id='VAR-000001'"
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
                INSERT INTO tpo.semine
                  (public_id,varieta_id,cultivar_id,cultivar_uso_id,lotto_seme_id,
                   protocollo_versione_id,stato,quantita_seme,unita_misura,
                   data_avvio,causa_origine,cultivar_snapshot,
                   uso_produttivo_snapshot,lotto_seme_snapshot,protocollo_snapshot,
                   created_by,codice_tracciabilita)
                SELECT 'SEM-000001',v.id,c.id,cu.id,l.id,pv.id,
                       'PRONTA_ALLA_RACCOLTA',1,'GRAM',
                       TIMESTAMPTZ '2026-08-25 08:00:00+00','ORDINE_CLIENTE',
                       'Afila','Microgreen','LOT-1','PV-000001','test','AFI-2508-A'
                FROM tpo.varieta v
                JOIN tpo.cultivar c ON c.varieta_id=v.id
                JOIN tpo.cultivar_usi cu ON cu.cultivar_id=c.id
                CROSS JOIN tpo.lotti_seme l
                CROSS JOIN tpo.protocollo_versioni pv
                WHERE v.public_id='VAR-000001' AND l.public_id='LSE-000001'
                  AND pv.public_id='PV-000001';
                INSERT INTO tpo.raccolte
                  (public_id,semina_id,data_raccolta,quantita,unita_misura,created_by)
                SELECT 'RAC-000001',id,TIMESTAMPTZ '2026-08-30 08:00:00+00',
                       0.5,'SET','legacy-test'
                FROM tpo.semine WHERE public_id='SEM-000001'
            """)
        with engine.connect() as connection:
            config = make_config(connection=connection)
            with pytest.raises(Exception, match="existing RACCOLTE require reconciliation"):
                alembic_command.upgrade(config, "20260830_0022")
            connection.rollback()
            assert connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one() == "20260826_0021"
            assert connection.exec_driver_sql(
                "SELECT public_id,quantita,unita_misura::text,created_by "
                "FROM tpo.raccolte"
            ).one() == ("RAC-000001", 0.5, "SET", "legacy-test")
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
