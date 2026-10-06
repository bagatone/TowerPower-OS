"""Real PostgreSQL: un run di planning COMMITTED con una raccolta in parte gia' caricata a magazzino.

Regressione 5/10/2026: il loader (fix B) offre alla pianificazione solo quantita - caricato, ma il commit
writer riconfrontava lo snapshot con la quantita' REGISTRATA della raccolta e falliva con
CONCURRENCY_CONFLICT HARVEST_CHANGED. Il caso non era coperto: nessun test pianificava con una raccolta caricata.
"""

from __future__ import annotations

from tests.integration.postgresql.test_production_planning_end_to_end import (
    _command, _scalar, _seed_identity, _service,
)
from tests.integration.postgresql.test_production_planning_end_to_end import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)


def _seed_loaded_harvest(engine, loaded: str) -> None:
    _seed_identity(engine)
    with engine.begin() as c:
        c.exec_driver_sql("""
        INSERT INTO tpo.ordini (public_id,cliente_id,data_ordine,data_consegna_prevista,stato,tipo_creazione,created_by,version)
        SELECT 'ORD-00000'||n,(SELECT id FROM tpo.clienti LIMIT 1),DATE '2026-08-01',(DATE '2026-08-10' + n),
               'APERTO','MANUALE','test',0 FROM generate_series(2,3) n;
        INSERT INTO tpo.righe_ordine (public_id,ordine_id,posizione,varieta_id,quantita,unita_misura,version)
        SELECT 'RO-00000'||n,o.id,1,(SELECT id FROM tpo.varieta LIMIT 1),1,'SET',0
        FROM generate_series(2,3) n JOIN tpo.ordini o ON o.public_id='ORD-00000'||n;
        UPDATE tpo.stock SET disponibile=0;
        """)
        c.exec_driver_sql("SET LOCAL session_replication_role = replica")
        c.exec_driver_sql("""
          INSERT INTO tpo.semine
            (public_id,varieta_id,cultivar_id,cultivar_uso_id,lotto_seme_id,protocollo_versione_id,stato,
             quantita_seme,unita_misura,data_avvio,causa_origine,cultivar_snapshot,uso_produttivo_snapshot,
             lotto_seme_snapshot,protocollo_snapshot,created_by,codice_tracciabilita)
          SELECT 'SEM-000901',id,1,1,1,1,'PRONTA_ALLA_RACCOLTA',10,'GRAM',TIMESTAMPTZ '2026-08-01 06:00+00',
                 'PIANO_PRODUZIONE','x','x','x','x','test','HVT-0108-A' FROM tpo.varieta LIMIT 1;
          INSERT INTO tpo.raccolte (public_id,semina_id,data_raccolta,quantita,unita_misura,created_by)
          SELECT 'RAC-000901',id,TIMESTAMPTZ '2026-08-10 06:00+00',2,'SET','test'
          FROM tpo.semine WHERE public_id='SEM-000901';
        """)
        c.exec_driver_sql(f"""
          INSERT INTO tpo.movimenti_magazzino
            (public_id,varieta_id,unita_misura,tipo,direzione,quantita,data_movimento,motivo,origine_tipo,
             raccolta_id,created_at,created_by)
          SELECT 'MOV-000901',s.varieta_id,'SET','CARICO','POSITIVO',{loaded},TIMESTAMPTZ '2026-08-10 07:00+00',
                 'carico da raccolta','RACCOLTA',rc.id,TIMESTAMPTZ '2026-08-10 07:00+00','test'
          FROM tpo.raccolte rc JOIN tpo.semine s ON s.id=rc.semina_id WHERE rc.public_id='RAC-000901'
        """)


def test_planning_commits_with_a_partly_loaded_harvest(planning_database):
    engine = planning_database
    _seed_loaded_harvest(engine, "1")          # 1 SET su 2 gia' a magazzino (e venduto: stock a 0)
    assert _service(engine).execute(_command("e2e-loaded-harvest")).run_state == "COMMITTED"
    # la raccolta offre solo la parte NON caricata: 1 SET di RACCOLTA allocato, non 2
    assert _scalar(engine, "SELECT COALESCE(SUM(a.quantity),0) FROM tpo.allocazioni a "
                           "WHERE a.allocation_type='RACCOLTA' AND a.state='ATTIVA'") == 1


def test_planning_commits_with_a_fully_loaded_harvest(planning_database):
    engine = planning_database
    _seed_loaded_harvest(engine, "2")          # tutta caricata e venduta: nulla da offrire come raccolta
    assert _service(engine).execute(_command("e2e-fully-loaded-harvest")).run_state == "COMMITTED"
    assert _scalar(engine, "SELECT count(*) FROM tpo.allocazioni WHERE allocation_type='RACCOLTA' "
                           "AND state='ATTIVA'") == 0
