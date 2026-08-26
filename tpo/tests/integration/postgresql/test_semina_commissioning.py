from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import time, uuid
from alembic import command as alembic_command
import pytest
import sqlalchemy as sa

from src.tpo_core.application.identity import CommissionIdentityRegistration, IdentityRegistrationCommissioningService
from src.tpo_core.application.semina_commissioning import CommissionSemina, PlannedSeminaStart, SeminaCommissioningAuthority, SeminaFactSource, SeminaOrigin
from src.tpo_core.application.semina_commissioning.errors import AnomalousSeedLotError, ExpiredSeedLotError, IncompatibleSeedLotError, InsufficientSeedError, PlanningLineNotFoundError, PlanningLineStateError, PlanningLineVersionConflictError, PlanningQuantityExceededError, ProtocolContextIncompatibleError, SeedLotVersionConflictError, SeminaCommitRolledBackError, SeminaIdempotencyConflictError, VarietyTraceabilityCodeUnavailableError
from src.tpo_core.domain.identifiers import ActorId, LottoSemeId, ProtocolloVersioneId, RigaPianoSeminaId, SeminaId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.identity_commissioning import PostgreSQLIdentityRegistrationCommissioningWriter
from src.tpo_core.infrastructure.postgresql.semina_commissioning import PostgreSQLSeminaCommissioningWriter
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory, _commit, _seed_authorities
from tests.infrastructure.postgresql.test_production_planning_migrations import isolated_postgresql

STARTED_AT = datetime(2026, 8, 25, 8, tzinfo=timezone.utc)
FACTS = ("physical_started_at", "actual_seed_grams", "selected_lse", "selected_pv", "origin")


@pytest.fixture
def environment(isolated_postgresql):
    cluster = isolated_postgresql.engine; name = f"tpo_semina_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as c: c.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    with engine.begin() as c:
        alembic_command.upgrade(make_config(connection=c), "head"); _seed_authorities(c)
        c.exec_driver_sql("UPDATE tpo.varieta SET codice_tracciabilita='AFI' WHERE public_id='VAR-000001'")
        c.exec_driver_sql("""
        INSERT INTO tpo.sementi(fornitore,referenza_commerciale,attiva,created_by,updated_at,updated_by,version)
        VALUES ('Supplier','REF',true,'test',CURRENT_TIMESTAMP,'test',0),('Other','OTHER',true,'test',CURRENT_TIMESTAMP,'test',0);
        INSERT INTO tpo.semente_impieghi(semente_id,cultivar_uso_id,raccomandazione,ultima_revisione,created_by,updated_at,updated_by,version)
        SELECT s.id,cu.id,'RACCOMANDATA',DATE '2026-08-25','test',CURRENT_TIMESTAMP,'test',0 FROM tpo.sementi s CROSS JOIN tpo.cultivar_usi cu WHERE s.fornitore='Supplier';
        INSERT INTO tpo.lotti_seme(public_id,semente_id,numero_lotto_produttore,data_ricezione,data_scadenza,quantita_iniziale,quantita_residua,unita_misura,anomalia,created_by,updated_at,updated_by,version)
        SELECT 'LSE-000001',id,'LOT-1',DATE '2026-08-24',NULL,10,10,'GRAM',NULL,'test',CURRENT_TIMESTAMP,'test',0 FROM tpo.sementi WHERE fornitore='Supplier';
        INSERT INTO tpo.lotti_seme(public_id,semente_id,numero_lotto_produttore,data_ricezione,data_scadenza,quantita_iniziale,quantita_residua,unita_misura,anomalia,created_by,updated_at,updated_by,version)
        SELECT 'LSE-000002',id,'LOT-2',DATE '2026-01-01',DATE '2026-08-24',5,5,'GRAM',NULL,'test',CURRENT_TIMESTAMP,'test',0 FROM tpo.sementi WHERE fornitore='Supplier';
        INSERT INTO tpo.lotti_seme(public_id,semente_id,numero_lotto_produttore,data_ricezione,data_scadenza,quantita_iniziale,quantita_residua,unita_misura,anomalia,created_by,updated_at,updated_by,version)
        SELECT 'LSE-000003',id,'LOT-3',DATE '2026-08-24',NULL,5,5,'GRAM','damaged','test',CURRENT_TIMESTAMP,'test',0 FROM tpo.sementi WHERE fornitore='Supplier';
        INSERT INTO tpo.lotti_seme(public_id,semente_id,numero_lotto_produttore,data_ricezione,quantita_iniziale,quantita_residua,unita_misura,created_by,updated_at,updated_by,version)
        SELECT 'LSE-000004',id,'LOT-4',DATE '2026-08-24',5,5,'GRAM','test',CURRENT_TIMESTAMP,'test',0 FROM tpo.sementi WHERE fornitore='Other';
        INSERT INTO tpo.lotti_seme(public_id,semente_id,numero_lotto_produttore,data_ricezione,quantita_iniziale,quantita_residua,unita_misura,created_by,updated_at,updated_by,version)
        SELECT 'LSE-000005',id,'LOT-5',DATE '2026-08-24',10,10,'GRAM','test',CURRENT_TIMESTAMP,'test',0 FROM tpo.sementi WHERE fornitore='Supplier';
        """)
    factory = _Factory(engine)
    IdentityRegistrationCommissioningService(PostgreSQLIdentityRegistrationCommissioningWriter(factory)).commission(
        CommissionIdentityRegistration(SeminaId.sequence_name, SeminaId, SeminaId.prefix, ActorId("identity")))
    _commit(engine)
    with engine.begin() as c: c.exec_driver_sql("UPDATE tpo.righe_piano_semina SET stato='PRONTA' WHERE public_id='RPS-000001'")
    try: yield engine, PostgreSQLSeminaCommissioningWriter(factory)
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as c: c.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')


def command(*, key="idem", lot="LSE-000001", lse_version=0, grams="1.25", origin=SeminaOrigin.ORDINE_CLIENTE, rps_version=0, sets="0.4", started_at=STARTED_AT):
    planning = None; facts = list(FACTS)
    if origin is SeminaOrigin.PIANO_PRODUZIONE:
        planning = PlannedSeminaStart(RigaPianoSeminaId("RPS-000001"), rps_version, Quantity(Decimal(sets), UnitOfMeasure.SET)); facts.append("planned_started_quantity")
    return CommissionSemina(LottoSemeId(lot), lse_version, ProtocolloVersioneId("PV-000001"), Quantity(Decimal(grams), UnitOfMeasure.GRAM), started_at, origin, planning, tuple((f, SeminaFactSource.OWNER_AUTHORIZED) for f in facts), SeminaCommissioningAuthority(ActorId("owner"), "physical start", f"corr-{key}", key))


def scalar(engine, sql):
    with engine.connect() as c: return c.exec_driver_sql(sql).scalar_one()


def outcome(writer, cmd):
    try: return writer.commission(cmd).outcome
    except Exception as exc: return type(exc)


def test_independent_success_identity_replay_audit_prediction_and_no_planning(environment):
    engine, writer = environment; first = writer.commission(command()); replay = writer.commission(command())
    assert first.semina_id == replay.semina_id == SeminaId("SEM-000001") and replay.outcome == "COMPATIBLE_REPLAY"
    assert first.traceability_code == replay.traceability_code
    assert first.traceability_code.value == "AFI-2508-A"
    with engine.connect() as c:
        semina = c.exec_driver_sql("SELECT stato,quantita_seme,unita_misura,esito_finale,expected_useful_quantity,expected_useful_uom,harvest_window_start,harvest_window_end FROM tpo.semine").one()
        lot = c.exec_driver_sql("SELECT quantita_residua,version FROM tpo.lotti_seme WHERE public_id='LSE-000001'").one()
        counts = c.exec_driver_sql("SELECT (SELECT count(*) FROM tpo.righe_piano_semina_semine),(SELECT count(*) FROM tpo.piano_produzione_revisioni),(SELECT count(*) FROM tpo.allocazioni),(SELECT count(*) FROM tpo.audit_eventi WHERE correlation_id='corr-idem')").one()
    assert semina == ("AVVIATA", Decimal("1.250000"), "GRAM", None, None, None, None, None)
    assert lot == (Decimal("8.750000"), 1) and counts == (0, 1, 1, 2)


def test_planned_partial_multiple_start_and_replay_are_exact(environment):
    engine, writer = environment
    first = writer.commission(command(key="p1", origin=SeminaOrigin.PIANO_PRODUZIONE)); replay = writer.commission(command(key="p1", origin=SeminaOrigin.PIANO_PRODUZIONE))
    second = writer.commission(command(key="p2", lse_version=1, origin=SeminaOrigin.PIANO_PRODUZIONE, rps_version=1, sets="0.6"))
    assert first.semina_id == replay.semina_id and second.semina_id == SeminaId("SEM-000002")
    with engine.connect() as c:
        rps = c.exec_driver_sql("SELECT stato,quantita_avviata,quantita_residua_da_avviare,version FROM tpo.righe_piano_semina WHERE public_id='RPS-000001'").one()
        links = c.exec_driver_sql("SELECT count(*),sum(quantita_avviata) FROM tpo.righe_piano_semina_semine").one()
    assert rps == ("AVVIATA", Decimal("1.000000"), Decimal("0.000000"), 2) and links == (2, Decimal("1.000000"))


def test_business_rejections_are_atomic(environment):
    engine, writer = environment
    cases = ((InsufficientSeedError,command(key="q",grams="11")),(SeedLotVersionConflictError,command(key="lv",lse_version=1)),(ExpiredSeedLotError,command(key="e",lot="LSE-000002")),(AnomalousSeedLotError,command(key="a",lot="LSE-000003")),(IncompatibleSeedLotError,command(key="i",lot="LSE-000004")),(PlanningQuantityExceededError,command(key="pq",origin=SeminaOrigin.PIANO_PRODUZIONE,sets="1.1")),(PlanningLineVersionConflictError,command(key="rv",origin=SeminaOrigin.PIANO_PRODUZIONE,rps_version=1)))
    for expected, cmd in cases:
        with pytest.raises(expected): writer.commission(cmd)
    assert scalar(engine,"SELECT count(*) FROM tpo.semine") == 0 and scalar(engine,"SELECT next_value FROM tpo.id_sequences WHERE sequence_name='SEMINA_ID'") == 1


def test_ineligible_planning_state_is_rejected(environment):
    engine, writer = environment
    with engine.begin() as c: c.exec_driver_sql("UPDATE tpo.righe_piano_semina SET stato='PIANIFICATA' WHERE public_id='RPS-000001'")
    with pytest.raises(PlanningLineStateError): writer.commission(command(origin=SeminaOrigin.PIANO_PRODUZIONE))
    assert scalar(engine,"SELECT count(*) FROM tpo.semine") == 0


@pytest.mark.parametrize(("mutation","expected"), [("UPDATE tpo.sementi SET attiva=false WHERE fornitore='Supplier'",IncompatibleSeedLotError),("UPDATE tpo.varieta SET stato='SOSPESA' WHERE public_id='VAR-000001'",ProtocolContextIncompatibleError),("UPDATE tpo.cultivar_usi SET stato_validazione='NON_APPROVATA'",ProtocolContextIncompatibleError),("UPDATE tpo.protocolli SET tipo='SPERIMENTALE'",ProtocolContextIncompatibleError)])
def test_inactive_or_experimental_authority_fails_closed(environment, mutation, expected):
    engine, writer = environment
    with engine.begin() as c: c.exec_driver_sql(mutation)
    with pytest.raises(expected): writer.commission(command())
    assert scalar(engine,"SELECT count(*) FROM tpo.semine") == 0


def test_idempotency_conflict_and_audit_failure_rollback(environment):
    engine, writer = environment; writer.commission(command())
    with pytest.raises(SeminaIdempotencyConflictError): writer.commission(command(grams="1.5"))
    with engine.begin() as c:
        c.exec_driver_sql("CREATE FUNCTION tpo.fail_semina_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.correlation_id='corr-audit-fail' THEN RAISE EXCEPTION 'audit failure'; END IF; RETURN NEW; END $$")
        c.exec_driver_sql("CREATE TRIGGER fail_semina_audit BEFORE INSERT ON tpo.audit_eventi FOR EACH ROW EXECUTE FUNCTION tpo.fail_semina_audit()")
    with pytest.raises(SeminaCommitRolledBackError): writer.commission(command(key="audit-fail",lse_version=1))
    assert scalar(engine,"SELECT count(*) FROM tpo.semine") == 1 and scalar(engine,"SELECT quantita_residua FROM tpo.lotti_seme WHERE public_id='LSE-000001'") == Decimal("8.750000")
    with engine.begin() as c: c.exec_driver_sql("DROP TRIGGER fail_semina_audit ON tpo.audit_eventi")
    recovered = writer.commission(command(key="after-rollback", lot="LSE-000005"))
    assert recovered.traceability_code.value == "AFI-2508-B"


def test_same_variety_day_allocates_next_letter_and_new_day_restarts_at_a(environment):
    _, writer = environment
    first = writer.commission(command(key="day-a"))
    second = writer.commission(command(key="day-b", lot="LSE-000005"))
    assert (first.traceability_code.value, second.traceability_code.value) == (
        "AFI-2508-A", "AFI-2508-B"
    )


def test_missing_variety_code_blocks_before_any_physical_write(environment):
    engine, writer = environment
    with engine.begin() as c:
        c.exec_driver_sql("ALTER TABLE tpo.varieta DISABLE TRIGGER protect_varieta_traceability_code")
        c.exec_driver_sql("UPDATE tpo.varieta SET codice_tracciabilita=NULL WHERE public_id='VAR-000001'")
        c.exec_driver_sql("ALTER TABLE tpo.varieta ENABLE TRIGGER protect_varieta_traceability_code")
    with pytest.raises(VarietyTraceabilityCodeUnavailableError):
        writer.commission(command(key="missing-code"))
    assert scalar(engine, "SELECT count(*) FROM tpo.semine") == 0


def test_concurrent_lse_and_last_seed_serialize(environment):
    engine, writer = environment
    with engine.begin() as c: c.exec_driver_sql("UPDATE tpo.lotti_seme SET quantita_residua=1,quantita_iniziale=1 WHERE public_id='LSE-000001'")
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(lambda n: outcome(writer,command(key=f"race-{n}",grams="1")),range(2)))
    assert results.count("INSERTED") == 1 and results.count(SeedLotVersionConflictError) == 1
    assert scalar(engine,"SELECT quantita_residua FROM tpo.lotti_seme WHERE public_id='LSE-000001'") == 0


def test_concurrent_independent_same_scope_gets_distinct_codes(environment):
    engine, writer = environment
    commands = (command(key="trace-race-a"), command(key="trace-race-b", lot="LSE-000005"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(writer.commission, commands))
    assert {result.traceability_code.value for result in results} == {"AFI-2508-A", "AFI-2508-B"}
    assert scalar(engine, "SELECT count(DISTINCT codice_tracciabilita) FROM tpo.semine") == 2


def test_concurrent_partial_starts_never_exceed_rps(environment):
    engine, writer = environment
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(lambda n: outcome(writer,command(key=f"rps-{n}",lot="LSE-000001" if n == 0 else "LSE-000005",origin=SeminaOrigin.PIANO_PRODUZIONE,sets="0.6")),range(2)))
    assert results.count("INSERTED") == 1 and results.count(PlanningLineVersionConflictError) == 1
    assert scalar(engine,"SELECT quantita_avviata FROM tpo.righe_piano_semina WHERE public_id='RPS-000001'") == Decimal("0.600000")


def test_concurrent_replan_cannot_use_superseded_rps(environment):
    engine, writer = environment; blocker = engine.connect(); tx = blocker.begin()
    blocker.exec_driver_sql("SELECT id FROM tpo.piani_produzione WHERE public_id='PP-000001' FOR UPDATE")
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(outcome,writer,command(key="replan",origin=SeminaOrigin.PIANO_PRODUZIONE)); time.sleep(.2)
        blocker.exec_driver_sql("UPDATE tpo.piani_produzione SET current_revision_id=NULL WHERE public_id='PP-000001'"); tx.commit(); result = future.result(timeout=5)
    blocker.close(); assert result is PlanningLineNotFoundError and scalar(engine,"SELECT count(*) FROM tpo.semine") == 0
