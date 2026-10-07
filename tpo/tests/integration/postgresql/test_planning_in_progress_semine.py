"""Real PostgreSQL: il planner vede le semine fisiche in corso (addendum 6/10/2026).

- una semina con finestra compatibile offre la sua resa attesa e il run va COMMITTED;
- una semina con finestra oltre la consegna e' SALTATA (non RESOURCE_NOT_READY);
- la resa gia' RACCOLTA non e' offerta due volte (eleggibile = attesa - raccolta), e il commit writer la rivalida.
"""

from __future__ import annotations

from tests.integration.postgresql.test_production_planning_end_to_end import (
    _command, _scalar, _seed_identity, _service,
)
from tests.integration.postgresql.test_production_planning_end_to_end import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)


def _seed(engine, semine, *, harvested_loaded: bool = False) -> None:
    """semine: (public_id, codice, attesa SET, inizio, fine, SET raccolti)."""
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
        for index, (public_id, code, expected, start, end, harvested) in enumerate(semine, start=1):
            c.exec_driver_sql(f"""
              INSERT INTO tpo.semine
                (public_id,varieta_id,cultivar_id,cultivar_uso_id,lotto_seme_id,protocollo_versione_id,stato,
                 quantita_seme,unita_misura,data_avvio,causa_origine,cultivar_snapshot,uso_produttivo_snapshot,
                 lotto_seme_snapshot,protocollo_snapshot,created_by,codice_tracciabilita,
                 expected_useful_quantity,expected_useful_uom,harvest_window_start,harvest_window_end)
              SELECT '{public_id}',id,1,1,1,1,'CRESCITA',10,'GRAM',TIMESTAMPTZ '2026-07-25 06:00+00',
                     'PIANO_PRODUZIONE','x','x','x','x','test','{code}',
                     {expected},'SET',TIMESTAMPTZ '{start} 06:00+00',TIMESTAMPTZ '{end} 06:00+00'
              FROM tpo.varieta LIMIT 1""")
            if harvested:
                c.exec_driver_sql(f"""
                  INSERT INTO tpo.raccolte (public_id,semina_id,data_raccolta,quantita,unita_misura,created_by)
                  SELECT 'RAC-00090{index}',id,TIMESTAMPTZ '2026-08-08 06:00+00',{harvested},'SET','test'
                  FROM tpo.semine WHERE public_id='{public_id}'""")
                if harvested_loaded:
                    c.exec_driver_sql(f"""
                      INSERT INTO tpo.movimenti_magazzino
                        (public_id,varieta_id,unita_misura,tipo,direzione,quantita,data_movimento,motivo,
                         origine_tipo,raccolta_id,created_at,created_by)
                      SELECT 'MOV-00090{index}',s.varieta_id,'SET','CARICO','POSITIVO',{harvested},
                             TIMESTAMPTZ '2026-08-08 07:00+00','carico da raccolta','RACCOLTA',rc.id,
                             TIMESTAMPTZ '2026-08-08 07:00+00','test'
                      FROM tpo.raccolte rc JOIN tpo.semine s ON s.id=rc.semina_id
                      WHERE rc.public_id='RAC-00090{index}'""")


def _in_progress_allocated(engine):
    return _scalar(engine, "SELECT COALESCE(SUM(quantity),0) FROM tpo.allocazioni "
                           "WHERE allocation_type='PRODUZIONE_IN_CORSO' AND state='ATTIVA'")


def test_compatible_semina_is_offered_and_late_semina_is_skipped(planning_database):
    engine = planning_database
    _seed(engine, [("SEM-000901", "HVT-0108-A", 1, "2026-08-05", "2026-08-10", 0),
                   ("SEM-000902", "HVT-0208-A", 5, "2026-08-25", "2026-08-30", 0)])
    assert _service(engine).execute(_command("e2e-in-progress")).run_state == "COMMITTED"
    assert _in_progress_allocated(engine) == 1          # solo la semina compatibile (1 SET); la tardiva e' saltata


def test_harvested_quantity_is_not_offered_twice(planning_database):
    engine = planning_database
    # attesa 3 SET, gia' raccolti 2 SET e caricati/venduti: restano 1 SET di produzione in corso
    _seed(engine, [("SEM-000901", "HVT-0108-A", 3, "2026-08-05", "2026-08-10", 2)], harvested_loaded=True)
    assert _service(engine).execute(_command("e2e-in-progress-net")).run_state == "COMMITTED"
    assert _in_progress_allocated(engine) == 1
