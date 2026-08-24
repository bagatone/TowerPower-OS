"""Integration contract del Production Planning Commit Writer."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
import hashlib
import inspect
import uuid
from zoneinfo import ZoneInfo

from alembic import command as alembic_command
import psycopg
import pytest
import sqlalchemy as sa

from src.tpo_core.application.production_planning.errors import (
    ProductionPlanningError,
    ProductionPlanningOutcomeUncertain,
)
from src.tpo_core.application.production_planning.models import (
    AllocationDraft,
    CanonicalHash,
    CanonicalReplanningSnapshot,
    PolicyVersionReference,
    ProductionPlanningRunSnapshot,
    PublicId,
    canonical_frame,
)
from src.tpo_core.domain.states import OrdineState
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.production_planning_commit_writer import (
    PostgreSQLProductionPlanningCommitWriter,
    _transition_facts,
)
from tests.application.production_planning.test_application_layer import (
    allocation_snapshot,
    allocation_transition,
    qty,
    write_set,
    zero_production_line,
)
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql as migration_postgresql,
)
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (
    _command as _delivery_command,
    _writer as _delivery_writer,
)


TZ = ZoneInfo("Atlantic/Canary")
PERSISTENCE_AT = datetime(2026, 8, 16, 7, 0, tzinfo=TZ)


class _Factory:
    def __init__(self, engine) -> None:
        self.url = engine.url

    def connect(self):
        return psycopg.connect(
            host=self.url.host, port=self.url.port, dbname=self.url.database,
            user=self.url.username, connect_timeout=5,
        )


@pytest.fixture(scope="module")
def writer_cluster(migration_postgresql):
    return migration_postgresql.engine


@pytest.fixture
def writer_database(writer_cluster):
    name = f"tpo_planning_writer_{uuid.uuid4().hex}"
    with writer_cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(writer_cluster.url.set(database=name))
    try:
        with engine.connect() as conn:
            alembic_command.upgrade(make_config(connection=conn), "head")
            _seed_authorities(conn)
            conn.commit()
        yield engine
    finally:
        engine.dispose()
        with writer_cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')


def _seed_authorities(conn) -> None:
    conn.exec_driver_sql("""
      INSERT INTO tpo.clienti
        (public_id,denominazione,created_by,updated_at,updated_by)
      VALUES ('CLI-000001','Writer test client','test',CURRENT_TIMESTAMP,'test');
      INSERT INTO tpo.varieta
        (public_id,denominazione,stato,created_by,updated_at,updated_by)
      VALUES ('VAR-000001','Writer test variety','ATTIVA','test',CURRENT_TIMESTAMP,'test');
      INSERT INTO tpo.cultivar
        (varieta_id,denominazione,stato,created_by,updated_at,updated_by)
      SELECT id,'Afila','ATTIVA','test',CURRENT_TIMESTAMP,'test'
      FROM tpo.varieta WHERE public_id='VAR-000001';
      INSERT INTO tpo.usi_produttivi
        (codice,denominazione,created_by,updated_at,updated_by)
      VALUES ('MICROGREEN','Microgreen','test',CURRENT_TIMESTAMP,'test');
      INSERT INTO tpo.cultivar_usi
        (cultivar_id,uso_produttivo_id,stato_validazione,created_by,updated_at,updated_by)
      SELECT c.id,u.id,'APPROVATA','test',CURRENT_TIMESTAMP,'test'
      FROM tpo.cultivar c CROSS JOIN tpo.usi_produttivi u
      WHERE c.denominazione='Afila' AND u.codice='MICROGREEN';
      INSERT INTO tpo.protocolli
        (cultivar_uso_id,tipo,denominazione,created_by,updated_at,updated_by)
      SELECT id,'STANDARD','Writer protocol','test',CURRENT_TIMESTAMP,'test'
      FROM tpo.cultivar_usi;
      INSERT INTO tpo.protocollo_versioni
        (public_id,protocollo_id,numero_versione,valida_dal,contenuto,motivazione,
         stato_approvazione,idratazione_ore,orario_semina_previsto,
         orario_raccolta_target,germinazione_giorni,crescita_luce_giorni,
         grammi_seme_per_set,resa_attesa,resa_unita_misura,
         granularita_produttiva,harvest_min_lead_giorni,
         harvest_max_lead_giorni,buffer_temporale_minuti,provenance,
         approvata_at,approvata_by,created_by)
      SELECT 'PV-000001',id,1,DATE '2026-01-01','writer','writer','APPROVATA',
             8,TIME '06:00',TIME '06:00',2,7,25,1,'SET',0.5,1,2,0,
             'approved-protocol',CURRENT_TIMESTAMP,'test','test'
      FROM tpo.protocolli;
      INSERT INTO tpo.production_planning_policy_versions
        (policy_set_code,numero_versione,harvest_target_strategy,
         buffer_quantitativo_tipo,priority_policy_code,planning_algorithm_version,
         valida_dal,provenance,approved_at,approved_by,created_by)
      VALUES ('DEFAULT',1,'EARLIEST_APPROVED_WINDOW','NONE',
              'DELIVERY_THEN_PUBLIC_ID','production-planning-v1',
              DATE '2026-01-01','test',CURRENT_TIMESTAMP,'test','test');
      INSERT INTO tpo.ordini
        (public_id,cliente_id,data_ordine,data_consegna_prevista,stato,
         tipo_creazione,created_by,version)
      SELECT 'ORD-000001',id,DATE '2026-08-01',DATE '2026-08-15',
             'APERTO','MANUALE','test',0 FROM tpo.clienti WHERE public_id='CLI-000001';
      INSERT INTO tpo.righe_ordine
        (public_id,ordine_id,posizione,varieta_id,quantita,unita_misura,version)
      SELECT 'RO-000001',o.id,1,v.id,1,'SET',0
      FROM tpo.ordini o CROSS JOIN tpo.varieta v
      WHERE o.public_id='ORD-000001' AND v.public_id='VAR-000001';
      INSERT INTO tpo.stock (varieta_id,disponibile,unita_misura,updated_at,version)
      SELECT id,2,'SET',CURRENT_TIMESTAMP,0
      FROM tpo.varieta WHERE public_id='VAR-000001';
      INSERT INTO tpo.production_planning_runs
        (public_id,policy_version_id,business_at,started_at,created_by,version)
      SELECT 'RPP-000001',id,TIMESTAMPTZ '2026-08-15 06:00:00+00',
             TIMESTAMPTZ '2026-08-16 06:30:00+01','tpo.planning',0
      FROM tpo.production_planning_policy_versions
      WHERE policy_set_code='DEFAULT' AND numero_versione=1;
    """)


def _commit(engine):
    run = ProductionPlanningRunSnapshot(
        public_id=PublicId("RPP-000001"),
        expected_version=0,
        state="OPEN",
    )
    value = write_set(run)
    writer = PostgreSQLProductionPlanningCommitWriter(_Factory(engine))
    return writer.commit(value, completed_at=PERSISTENCE_AT), value


def _zero_production_write_set(run, *, mixed: bool = False):
    base = write_set(run)
    line = zero_production_line(
        stock="0.4", in_progress="0.3", harvest="0.3"
    ) if mixed else zero_production_line()
    return replace(
        base,
        revisions=(replace(base.revisions[0], lines=(line,)),),
        seed_resources=(),
    )


def _open_run(engine, number: int) -> ProductionPlanningRunSnapshot:
    public_id = f"RPP-{number:06d}"
    with engine.begin() as conn:
        conn.execute(sa.text("""
          INSERT INTO tpo.production_planning_runs
            (public_id,policy_version_id,business_at,started_at,created_by,version)
          SELECT :public_id,id,TIMESTAMPTZ '2026-08-15 06:00:00+00',
                 TIMESTAMPTZ '2026-08-16 06:30:00+01','tpo.planning',0
          FROM tpo.production_planning_policy_versions
          WHERE policy_set_code='DEFAULT' AND numero_versione=1
        """), {"public_id": public_id})
    return ProductionPlanningRunSnapshot(PublicId(public_id), 0, "OPEN")


def _authorize_empty_disposition_set(engine, key: str) -> None:
    with engine.begin() as conn:
        conn.execute(sa.text("""
          INSERT INTO tpo.replanning_disposition_sets
            (decision_set_key,previous_plan_revision_id,order_line_id,
             replanning_reason_code,correlation_id,state,authorized_at,
             authorized_by,provenance,created_by)
          SELECT :key,r.id,ro.id,'STOCK_CHANGED','writer-replan-001',
                 'AUTHORIZED',CURRENT_TIMESTAMP,'test','writer-test','test'
          FROM tpo.piano_produzione_revisioni r
          JOIN tpo.righe_ordine ro ON ro.public_id='RO-000001'
          WHERE r.public_id='RVP-000001'
        """), {"key": key})


def _transition_write_set(engine, transition, *, replacement=None, run_number=2):
    _commit(engine)
    run = _open_run(engine, run_number)
    base = write_set(run)
    snapshot = replace(base.input_snapshot, allocations=(allocation_snapshot(),))
    allocations = base.allocations
    if replacement is not None:
        allocations = (*allocations, replacement)
    counters = replace(base.counters, allocations_generated=len(allocations))
    return replace(
        base, input_snapshot=snapshot, allocations=allocations,
        allocation_transitions=(transition,), counters=counters,
    )


def _assert_zero_partial_writes(engine, run_id="RPP-000001") -> None:
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.piani_produzione").scalar_one() == 0
        assert conn.execute(sa.text(
            "SELECT state FROM tpo.production_planning_runs WHERE public_id=:run"
        ), {"run": run_id}).scalar_one() == "OPEN"
        assert conn.exec_driver_sql("SELECT 1").scalar_one() == 1


def test_initial_commit_complete_audit_run_and_deferred_constraints(writer_database) -> None:
    result, value = _commit(writer_database)
    assert result.run_state == "COMMITTED"
    assert result.committed_at == PERSISTENCE_AT
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql(
            "SELECT state,version,completed_at FROM tpo.production_planning_runs WHERE public_id='RPP-000001'"
        ).one() == ("COMMITTED", 1, PERSISTENCE_AT)
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.piani_produzione").scalar_one() == 1
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.piano_produzione_revisioni").scalar_one() == 1
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.righe_piano_semina").scalar_one() == 1
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.risorse_seme_pianificate").scalar_one() == 1
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.allocazioni").scalar_one() == 1
        audit = conn.exec_driver_sql(
            "SELECT actor,reason,correlation_id,provenance,occurred_at FROM tpo.audit_eventi ORDER BY id"
        ).all()
        assert len(audit) == len(value.audits)
        assert all(row[:3] == ("tpo.planning", "planning", "corr-1") for row in audit)
        assert all(row[3] and row[4] == PERSISTENCE_AT for row in audit)


@pytest.mark.parametrize("mixed", [False, True], ids=["stock", "mixed"])
def test_zero_production_line_persists_without_seed_child(
    writer_database, mixed: bool,
) -> None:
    run = ProductionPlanningRunSnapshot(PublicId("RPP-000001"), 0, "OPEN")
    value = _zero_production_write_set(run, mixed=mixed)
    result = PostgreSQLProductionPlanningCommitWriter(
        _Factory(writer_database)
    ).commit(value, completed_at=PERSISTENCE_AT)
    assert result.run_state == "COMMITTED"
    with writer_database.connect() as conn:
        row = conn.exec_driver_sql("""
          SELECT quantita_produttiva_autorizzata,grammi_seme_richiesti,
                 copertura_stock,copertura_produzione_in_corso,
                 copertura_raccolta_allocata
          FROM tpo.righe_piano_semina WHERE public_id='RPS-000001'
        """).one()
        assert row[0:2] == (Decimal("0"), None)
        assert sum(row[2:]) == Decimal("1")
        assert conn.exec_driver_sql(
            "SELECT count(*) FROM tpo.risorse_seme_pianificate"
        ).scalar_one() == 0
        assert conn.exec_driver_sql(
            "SELECT count(*) FROM tpo.allocazioni"
        ).scalar_one() == 1
        assert conn.exec_driver_sql(
            "SELECT count(*) FROM tpo.audit_eventi WHERE planning_run_id IS NOT NULL"
        ).scalar_one() == len(value.audits)


def test_mixed_revision_persists_exactly_one_positive_seed_child(
    writer_database,
) -> None:
    run = ProductionPlanningRunSnapshot(PublicId("RPP-000001"), 0, "OPEN")
    base = _multi_plan_write_set(run)
    zero_line = zero_production_line()
    zero_revision = replace(base.revisions[0], lines=(zero_line,))
    positive_seed = tuple(
        resource for resource in base.seed_resources
        if resource.planning_line_public_id == base.revisions[1].lines[0].public_id
    )
    value = replace(
        base,
        revisions=(zero_revision, base.revisions[1]),
        seed_resources=positive_seed,
    )
    PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(
        value, completed_at=PERSISTENCE_AT
    )
    with writer_database.connect() as conn:
        rows = conn.exec_driver_sql("""
          SELECT r.public_id,r.quantita_produttiva_autorizzata,
                 r.grammi_seme_richiesti,count(s.id)
          FROM tpo.righe_piano_semina r
          LEFT JOIN tpo.risorse_seme_pianificate s
            ON s.riga_piano_semina_id=r.id
          GROUP BY r.id ORDER BY r.public_id
        """).all()
    assert rows == [
        ("RPS-000001", Decimal("0"), None, 0),
        ("RPS-000002", Decimal("1"), Decimal("25"), 1),
    ]


@pytest.mark.parametrize(
    ("mutation", "code"),
    (
        ("UPDATE tpo.ordini SET version=1 WHERE public_id='ORD-000001'", "ORDER_CHANGED"),
        ("UPDATE tpo.righe_ordine SET version=1 WHERE public_id='RO-000001'", "ORDER_LINE_FULFILMENT_CHANGED"),
        ("UPDATE tpo.production_planning_policy_versions SET priority_policy_code='CHANGED' WHERE policy_set_code='DEFAULT'", "POLICY_CHANGED"),
        ("UPDATE tpo.protocollo_versioni SET buffer_temporale_minuti=1 WHERE public_id='PV-000001'", "PROTOCOL_CHANGED"),
    ),
)
def test_revalidation_conflicts_rollback_and_connection_health(
    writer_database, mutation: str, code: str,
) -> None:
    with writer_database.begin() as conn:
        conn.exec_driver_sql(mutation)
    with pytest.raises(ProductionPlanningError) as captured:
        _commit(writer_database)
    assert captured.value.code == code
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql("SELECT 1").scalar_one() == 1
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.piani_produzione").scalar_one() == 0
        assert conn.exec_driver_sql("SELECT state FROM tpo.production_planning_runs").scalar_one() == "OPEN"


def test_delivered_residual_changed_is_revalidated_under_lock(writer_database) -> None:
    delivery = _delivery_writer(writer_database).publish(
        _delivery_command(1, "0.25", movement=1)
    )
    assert delivery.order_states[0][1] == "PARZIALMENTE_EVASO"
    with pytest.raises(ProductionPlanningError) as captured:
        _commit(writer_database)
    assert captured.value.category == "CONCURRENCY_CONFLICT"
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql("SELECT stato,version FROM tpo.ordini WHERE public_id='ORD-000001'").one() == ("PARZIALMENTE_EVASO", 1)
        assert conn.exec_driver_sql("SELECT version FROM tpo.righe_ordine WHERE public_id='RO-000001'").scalar_one() == 1
        assert conn.exec_driver_sql("SELECT COALESCE(SUM(quantita),0) FROM tpo.righe_consegna").scalar_one() == Decimal("0.25")
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.piani_produzione").scalar_one() == 0
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.audit_eventi WHERE planning_run_id IS NOT NULL").scalar_one() == 0
        assert conn.exec_driver_sql("SELECT state FROM tpo.production_planning_runs WHERE public_id='RPP-000001'").scalar_one() == "OPEN"
        assert conn.exec_driver_sql("SELECT 1").scalar_one() == 1


def test_port_signature_and_provider_boundary() -> None:
    signature = inspect.signature(PostgreSQLProductionPlanningCommitWriter.commit)
    assert tuple(signature.parameters) == ("self", "write_set", "completed_at")
    source = inspect.getsource(PostgreSQLProductionPlanningCommitWriter)
    for forbidden in ("sqlalchemy", "google", "requests", "eval("):
        assert forbidden not in source.lower()
    for authority in (
        "UPDATE tpo.ordini", "UPDATE tpo.righe_ordine", "UPDATE tpo.stock",
        "UPDATE tpo.semine", "UPDATE tpo.raccolte", "UPDATE tpo.movimenti_magazzino",
    ):
        assert authority not in source
    assert "candidate.productive_quantity" not in source
    assert "authorized_productive_quantity" in source


def test_resource_authority_revalidation_contract_is_explicit() -> None:
    source = inspect.getsource(
        PostgreSQLProductionPlanningCommitWriter._lock_and_revalidate_inputs
    )
    assert "readiness_code" not in source
    for field in (
        "expected_useful_quantity", "expected_useful_uom",
        "harvest_window_start", "harvest_window_end",
    ):
        assert field in source


def test_completed_at_naive_fails_before_connection() -> None:
    run = ProductionPlanningRunSnapshot(
        public_id=PublicId("RPP-000001"), expected_version=0, state="OPEN",
    )
    class _MustNotConnect:
        def connect(self):
            raise AssertionError("La validazione deve precedere la connessione.")

    writer = PostgreSQLProductionPlanningCommitWriter(_MustNotConnect())
    with pytest.raises(ProductionPlanningError) as captured:
        writer.commit(write_set(run), completed_at=datetime(2026, 8, 10, 7))
    assert captured.value.code == "INVALID_PERSISTENCE_TIME"


@pytest.mark.parametrize(
    ("overrides", "expected_type"),
    (
        ({"consumed_quantity_delta": "1", "target_state": "CONSUMATA"}, "CONSUMATA"),
        ({"consumed_quantity_delta": "0", "released_quantity_delta": "1", "target_state": "RILASCIATA"}, "RILASCIATA"),
        ({"consumed_quantity_delta": "0", "invalidated_quantity_delta": "1", "target_state": "INVALIDA"}, "INVALIDA"),
    ),
)
def test_transition_fact_mapping_is_exact(overrides, expected_type) -> None:
    draft = allocation_transition(**overrides)
    assert _transition_facts(draft, None) == (
        (expected_type, draft.observed_allocated_quantity, None,
         draft.reason, draft.provenance),
    )


def test_transfer_fact_requires_the_resolved_replacement_pk() -> None:
    draft = allocation_transition(
        consumed_quantity_delta="0", transferred_quantity_delta="1",
        target_state="SOSTITUITA",
        replacement_allocation_public_id=PublicId("ALL-000002"),
    )
    assert _transition_facts(draft, 42) == (
        ("SOSTITUITA", draft.transferred_quantity_delta, 42,
         draft.reason, draft.provenance),
    )


def test_compatible_revision_replay_reuses_revision(writer_database) -> None:
    first, _ = _commit(writer_database)
    run = _open_run(writer_database, 2)
    replay = write_set(run)
    result = PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(
        replay, completed_at=PERSISTENCE_AT
    )
    assert first.current_revision_public_ids == result.current_revision_public_ids
    assert result.revision_results[0].reused_existing_revision is True
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.piano_produzione_revisioni").scalar_one() == 1


def test_compatible_revision_replay_ignores_new_writer_owned_result_ids(
    writer_database,
) -> None:
    first, original = _commit(writer_database)
    run = _open_run(writer_database, 2)
    revision = original.revisions[0]
    old_line = revision.lines[0]
    new_line_id = PublicId("RPS-000002")
    replay = replace(
        original,
        run=run,
        revisions=(replace(
            revision,
            plan_public_id=PublicId("PP-000002"),
            revision_public_id=PublicId("RVP-000002"),
            lines=(replace(old_line, public_id=new_line_id),),
        ),),
        allocations=tuple(
            replace(
                allocation,
                public_id=PublicId("ALL-000002"),
                planning_line_public_id=new_line_id,
            )
            for allocation in original.allocations
        ),
        seed_resources=tuple(
            replace(resource, planning_line_public_id=new_line_id)
            for resource in original.seed_resources
        ),
    )

    result = PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(
        replay, completed_at=PERSISTENCE_AT
    )

    assert result.plan_public_ids == first.plan_public_ids
    assert result.current_revision_public_ids == first.current_revision_public_ids
    assert result.planning_line_public_ids == first.planning_line_public_ids
    assert result.allocation_public_ids == first.allocation_public_ids
    assert result.revision_results[0].reused_existing_revision is True
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql(
            "SELECT count(*) FROM tpo.piano_produzione_revisioni"
        ).scalar_one() == 1
        assert conn.exec_driver_sql(
            "SELECT count(*) FROM tpo.righe_piano_semina"
        ).scalar_one() == 1
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.allocazioni").scalar_one() == 1


def test_replayed_revision_rejects_changed_allocation_material_facts(
    writer_database,
) -> None:
    _, original = _commit(writer_database)
    old_revision = original.revisions[0]
    old_line = old_revision.lines[0]
    new_line_id = PublicId("RPS-000002")
    replay = replace(
        original,
        run=_open_run(writer_database, 2),
        revisions=(replace(
            old_revision,
            plan_public_id=PublicId("PP-000002"),
            revision_public_id=PublicId("RVP-000002"),
            lines=(replace(old_line, public_id=new_line_id),),
        ),),
        allocations=(replace(
            original.allocations[0],
            public_id=PublicId("ALL-000002"),
            planning_line_public_id=new_line_id,
            quantity=qty("0.5"),
        ),),
        seed_resources=tuple(
            replace(resource, planning_line_public_id=new_line_id)
            for resource in original.seed_resources
        ),
    )

    with pytest.raises(ProductionPlanningError) as captured:
        PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(
            replay, completed_at=PERSISTENCE_AT
        )

    assert captured.value.code == "ALLOCATION_REPLAY_MISMATCH"


def test_zero_production_replay_reuses_line_without_creating_seed_child(
    writer_database,
) -> None:
    writer = PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database))
    first = _zero_production_write_set(
        ProductionPlanningRunSnapshot(PublicId("RPP-000001"), 0, "OPEN")
    )
    writer.commit(first, completed_at=PERSISTENCE_AT)
    replay = _zero_production_write_set(_open_run(writer_database, 2))
    result = writer.commit(replay, completed_at=PERSISTENCE_AT)
    assert result.revision_results[0].reused_existing_revision is True
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql(
            "SELECT count(*) FROM tpo.risorse_seme_pianificate"
        ).scalar_one() == 0
        assert conn.exec_driver_sql("SELECT 1").scalar_one() == 1


def test_zero_production_replay_rejects_unexpected_seed_child(
    writer_database,
) -> None:
    writer = PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database))
    first = _zero_production_write_set(
        ProductionPlanningRunSnapshot(PublicId("RPP-000001"), 0, "OPEN")
    )
    writer.commit(first, completed_at=PERSISTENCE_AT)
    with writer_database.begin() as conn:
        conn.exec_driver_sql("""
          INSERT INTO tpo.risorse_seme_pianificate
            (riga_piano_semina_id,cultivar_uso_id,protocollo_versione_id,
             grammi_richiesti,grammi_seme_per_set,unita_misura,created_by)
          SELECT r.id,r.cultivar_uso_id,p.id,25,25,'GRAM','test'
          FROM tpo.righe_piano_semina r
          CROSS JOIN tpo.protocollo_versioni p
          WHERE r.public_id='RPS-000001' AND p.public_id='PV-000001'
        """)
    replay = _zero_production_write_set(_open_run(writer_database, 2))
    with pytest.raises(ProductionPlanningError) as captured:
        writer.commit(replay, completed_at=PERSISTENCE_AT)
    assert captured.value.code == "REVISION_REPLAY_MISMATCH"
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql(
            "SELECT state FROM tpo.production_planning_runs WHERE public_id='RPP-000002'"
        ).scalar_one() == "OPEN"
        assert conn.exec_driver_sql("SELECT 1").scalar_one() == 1


def test_positive_production_replay_rejects_missing_seed_child(
    writer_database,
) -> None:
    writer = PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database))
    _, first = _commit(writer_database)
    with writer_database.begin() as conn:
        conn.exec_driver_sql("DELETE FROM tpo.risorse_seme_pianificate")
    replay = replace(first, run=_open_run(writer_database, 2))
    with pytest.raises(ProductionPlanningError) as captured:
        writer.commit(replay, completed_at=PERSISTENCE_AT)
    assert captured.value.code == "REVISION_REPLAY_MISMATCH"
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql(
            "SELECT state FROM tpo.production_planning_runs WHERE public_id='RPP-000002'"
        ).scalar_one() == "OPEN"
        assert conn.exec_driver_sql("SELECT 1").scalar_one() == 1


def test_incompatible_revision_replay_rolls_back(writer_database) -> None:
    _commit(writer_database)
    run = _open_run(writer_database, 2)
    base = write_set(run)
    changed_line = replace(
        base.revisions[0].lines[0],
        planning_key=type(base.revisions[0].lines[0].planning_key)("c" * 64),
    )
    changed_revision = replace(base.revisions[0], lines=(changed_line,))
    changed = replace(base, revisions=(changed_revision,))
    with pytest.raises(ProductionPlanningError) as captured:
        PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(
            changed, completed_at=PERSISTENCE_AT
        )
    assert captured.value.code == "REVISION_REPLAY_MISMATCH"
    with writer_database.connect() as conn:
        assert conn.execute(sa.text(
            "SELECT state FROM tpo.production_planning_runs WHERE public_id='RPP-000002'"
        )).scalar_one() == "OPEN"


def test_partial_allocation_consume(writer_database) -> None:
    transition = allocation_transition()
    value = _transition_write_set(writer_database, transition)
    PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(
        value, completed_at=PERSISTENCE_AT
    )
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql("SELECT state,version FROM tpo.allocazioni WHERE public_id='ALL-000001'").one() == ("ATTIVA", 1)
        assert conn.exec_driver_sql("SELECT transition_type,quantity FROM tpo.transizioni_allocazione").one() == ("CONSUMATA", transition.consumed_quantity_delta)


def test_full_allocation_consume(writer_database) -> None:
    transition = allocation_transition(consumed_quantity_delta="1", target_state="CONSUMATA")
    value = _transition_write_set(writer_database, transition)
    PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(value, completed_at=PERSISTENCE_AT)
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql("SELECT state,version FROM tpo.allocazioni WHERE public_id='ALL-000001'").one() == ("CONSUMATA", 1)


def test_release_residual_after_consumption(writer_database) -> None:
    transition = allocation_transition(
        consumed_quantity_delta="0.4", released_quantity_delta="0.6",
        target_state="RILASCIATA",
    )
    value = _transition_write_set(writer_database, transition)
    PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(value, completed_at=PERSISTENCE_AT)
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql("SELECT state FROM tpo.allocazioni WHERE public_id='ALL-000001'").scalar_one() == "RILASCIATA"
        assert {row[0] for row in conn.exec_driver_sql("SELECT transition_type FROM tpo.transizioni_allocazione")} == {"CONSUMATA", "RILASCIATA"}


def test_partial_allocation_invalidation(writer_database) -> None:
    transition = allocation_transition(
        consumed_quantity_delta="0", invalidated_quantity_delta="0.4",
        target_state="ATTIVA",
    )
    value = _transition_write_set(writer_database, transition)
    PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(value, completed_at=PERSISTENCE_AT)
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql("SELECT state,version FROM tpo.allocazioni WHERE public_id='ALL-000001'").one() == ("ATTIVA", 1)


def test_full_allocation_invalidation(writer_database) -> None:
    transition = allocation_transition(
        consumed_quantity_delta="0", invalidated_quantity_delta="1",
        target_state="INVALIDA",
    )
    value = _transition_write_set(writer_database, transition)
    PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(value, completed_at=PERSISTENCE_AT)
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql("SELECT state FROM tpo.allocazioni WHERE public_id='ALL-000001'").scalar_one() == "INVALIDA"


def test_transfer_residual_creates_typed_replacement(writer_database) -> None:
    transition = allocation_transition(
        consumed_quantity_delta="0.4", transferred_quantity_delta="0.6",
        target_state="SOSTITUITA",
        replacement_allocation_public_id=PublicId("ALL-000002"),
    )
    replacement = AllocationDraft(
        PublicId("ALL-000002"), "DOMANDA", PublicId("RPS-000001"),
        PublicId("RO-000001"), PublicId("RO-000001"), qty("0.6"),
    )
    value = _transition_write_set(writer_database, transition, replacement=replacement)
    PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(value, completed_at=PERSISTENCE_AT)
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql("SELECT state FROM tpo.allocazioni WHERE public_id='ALL-000001'").scalar_one() == "SOSTITUITA"
        assert conn.exec_driver_sql("SELECT quantity FROM tpo.allocazioni WHERE public_id='ALL-000002'").scalar_one() == transition.transferred_quantity_delta
        assert conn.exec_driver_sql("SELECT replacement_allocation_id IS NOT NULL FROM tpo.transizioni_allocazione WHERE transition_type='SOSTITUITA'").scalar_one()


def test_observed_allocation_balance_mismatch_is_atomic(writer_database) -> None:
    transition = allocation_transition(
        observed_consumed_quantity="0.1", observed_remaining_quantity="0.9",
        consumed_quantity_delta="0.1", target_state="ATTIVA",
    )
    value = _transition_write_set(writer_database, transition)
    with pytest.raises(ProductionPlanningError) as captured:
        PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(value, completed_at=PERSISTENCE_AT)
    assert captured.value.code in {"ALLOCATION_SNAPSHOT_CHANGED", "ALLOCATION_BALANCE_CHANGED"}
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.transizioni_allocazione").scalar_one() == 0
        assert conn.exec_driver_sql("SELECT 1").scalar_one() == 1


def test_over_transition_produces_zero_partial_writes(writer_database) -> None:
    transition = allocation_transition(consumed_quantity_delta="1", target_state="CONSUMATA")
    value = _transition_write_set(writer_database, transition)
    with writer_database.begin() as conn:
        allocation_id = conn.exec_driver_sql("SELECT id FROM tpo.allocazioni WHERE public_id='ALL-000001'").scalar_one()
        conn.execute(sa.text("""
          INSERT INTO tpo.transizioni_allocazione
            (allocation_id,transition_type,quantity,expected_allocation_version,
             created_by,reason,provenance)
          VALUES (:id,'CONSUMATA',0.5,99,'test','test','test')
        """), {"id": allocation_id})
    with pytest.raises(ProductionPlanningError):
        PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(value, completed_at=PERSISTENCE_AT)
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.transizioni_allocazione").scalar_one() == 1
        assert conn.exec_driver_sql("SELECT state FROM tpo.production_planning_runs WHERE public_id='RPP-000002'").scalar_one() == "OPEN"


def test_historical_business_time_is_distinct_from_persistence_time(writer_database) -> None:
    result, _ = _commit(writer_database)
    with writer_database.connect() as conn:
        business_at, completed_at = conn.exec_driver_sql(
            "SELECT business_at,completed_at FROM tpo.production_planning_runs WHERE public_id='RPP-000001'"
        ).one()
    assert business_at != completed_at
    assert result.committed_at == PERSISTENCE_AT


def test_version_increments_exactly_once_per_affected_aggregate(writer_database) -> None:
    _commit(writer_database)
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql("SELECT version FROM tpo.production_planning_runs WHERE public_id='RPP-000001'").scalar_one() == 1
        assert conn.exec_driver_sql("SELECT version FROM tpo.piani_produzione WHERE public_id='PP-000001'").scalar_one() == 1
        assert conn.exec_driver_sql("SELECT version FROM tpo.piano_produzione_revisioni WHERE public_id='RVP-000001'").scalar_one() == 0
        assert conn.exec_driver_sql("SELECT version FROM tpo.allocazioni WHERE public_id='ALL-000001'").scalar_one() == 0


def test_replanning_snapshot_0011_balances_are_persisted_field_by_field(writer_database) -> None:
    _commit(writer_database)
    _authorize_empty_disposition_set(writer_database, "c" * 64)
    run = _open_run(writer_database, 2)
    base = write_set(run)
    canonical_text = "TPO-REPLANNING-V1|ORDER=ORD-000001" + canonical_frame("c" * 64)
    snapshot = CanonicalReplanningSnapshot(
        previous_revision_public_id=PublicId("RVP-000001"),
        previous_plan_revision_version=0,
        order_line_public_id=PublicId("RO-000001"),
        order_public_id=PublicId("ORD-000001"), order_state=OrdineState.APERTO,
        order_version=0, order_line_version=0, ordered_quantity=qty("1"),
        delivered_quantity=qty("0"), commercial_residual_quantity=qty("1"),
        delivery_date=date(2026, 8, 15), variety_public_id=PublicId("VAR-000001"),
        protocol_version_public_id=PublicId("PV-000001"), protocol_version_number=1,
        protocol_valid_from=date(2026, 1, 1), protocol_valid_to=None,
        reason_code="STOCK_CHANGED", policy=PolicyVersionReference("DEFAULT", 1),
        quantitative_buffer_type="NONE", quantitative_buffer_value=None,
        temporal_buffer_minutes=0, production_granularity=Decimal("0.5"),
        stock=(), in_progress=(), allocations=(allocation_snapshot(),),
        decision_set_key=CanonicalHash("c" * 64),
        canonical_text=canonical_text,
        canonical_snapshot_hash=CanonicalHash(hashlib.sha256(canonical_text.encode()).hexdigest()),
        replanning_key_v1=CanonicalHash("b" * 64),
    )
    line = replace(
        base.revisions[0].lines[0], public_id=PublicId("RPS-000002"),
        planning_key=CanonicalHash("b" * 64),
    )
    revision = replace(
        base.revisions[0], revision_public_id=PublicId("RVP-000002"),
        revision_number=2, request_key=CanonicalHash("b" * 64), lines=(line,),
        expected_plan_version=1, expected_current_revision_version=0,
        previous_revision_public_id=PublicId("RVP-000001"),
        replanning_reason_code="STOCK_CHANGED", canonical_replanning_snapshot=snapshot,
    )
    value = replace(
        base, revisions=(revision,),
        seed_resources=(replace(base.seed_resources[0], planning_line_public_id=line.public_id),),
        allocations=(), allocation_transitions=(),
        counters=replace(base.counters, allocations_generated=0),
        input_snapshot=replace(base.input_snapshot, allocations=(allocation_snapshot(),)),
    )
    PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(value, completed_at=PERSISTENCE_AT)
    with writer_database.connect() as conn:
        row = conn.exec_driver_sql("""
          SELECT allocated_quantity,consumed_quantity,released_quantity,
                 transferred_quantity,invalidated_quantity,remaining_quantity
          FROM tpo.replanning_snapshot_allocazioni
        """).one()
    assert row == (Decimal("1"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("1"))


def test_audit_provenance_and_context_are_atomic(writer_database) -> None:
    _, value = _commit(writer_database)
    with writer_database.connect() as conn:
        rows = conn.exec_driver_sql("SELECT actor,reason,correlation_id,provenance FROM tpo.audit_eventi ORDER BY id").all()
    assert len(rows) == len(value.audits)
    assert all(row[0:3] == ("tpo.planning", "planning", "corr-1") and row[3] for row in rows)


def test_audit_failure_rolls_back_business_writes(writer_database) -> None:
    run = ProductionPlanningRunSnapshot(PublicId("RPP-000001"), 0, "OPEN")
    value = write_set(run)
    bad_audit = replace(value.audits[0], provenance="valid-at-model")
    with writer_database.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE tpo.audit_eventi ADD CONSTRAINT test_reject_audit CHECK (provenance <> 'valid-at-model')")
    with pytest.raises(ProductionPlanningError):
        PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(
            replace(value, audits=(bad_audit, *value.audits[1:])),
            completed_at=PERSISTENCE_AT,
        )
    _assert_zero_partial_writes(writer_database)


def _multi_plan_write_set(run):
    base = write_set(run)
    line2 = replace(
        base.revisions[0].lines[0], public_id=PublicId("RPS-000002"),
        planning_key=type(base.revisions[0].request_key)("d" * 64),
    )
    revision2 = replace(
        base.revisions[0], plan_public_id=PublicId("PP-000002"),
        revision_public_id=PublicId("RVP-000002"), request_key=type(base.revisions[0].request_key)("e" * 64),
        lines=(line2,),
    )
    seed2 = replace(base.seed_resources[0], planning_line_public_id=line2.public_id)
    audit2 = replace(base.audits[0], entity_public_id=PublicId("PP-000002"))
    audits = tuple(sorted((*base.audits, audit2), key=lambda item: (
        item.entity_type, item.entity_public_id.value, item.operation,
    )))
    return replace(
        base, revisions=(*base.revisions, revision2),
        seed_resources=(*base.seed_resources, seed2),
        counters=replace(base.counters, planning_lines_generated=2), audits=audits,
    )


def test_multi_plan_commit_is_atomic(writer_database) -> None:
    run = ProductionPlanningRunSnapshot(PublicId("RPP-000001"), 0, "OPEN")
    value = _multi_plan_write_set(run)
    result = PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(value, completed_at=PERSISTENCE_AT)
    assert tuple(item.value for item in result.plan_public_ids) == ("PP-000001", "PP-000002")
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.piani_produzione").scalar_one() == 2


def test_multi_revision_result_is_deterministically_associated(writer_database) -> None:
    run = ProductionPlanningRunSnapshot(PublicId("RPP-000001"), 0, "OPEN")
    result = PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(
        _multi_plan_write_set(run), completed_at=PERSISTENCE_AT
    )
    assert tuple((item.plan_public_id.value, item.revision_public_id.value) for item in result.revision_results) == (
        ("PP-000001", "RVP-000001"), ("PP-000002", "RVP-000002"),
    )


def test_multi_line_multi_order_lock_inputs_are_sorted(writer_database) -> None:
    with writer_database.begin() as conn:
        conn.exec_driver_sql("""
          INSERT INTO tpo.ordini
            (public_id,cliente_id,data_ordine,data_consegna_prevista,stato,
             tipo_creazione,created_by,version)
          SELECT 'ORD-000002',id,DATE '2026-08-01',DATE '2026-08-16',
                 'APERTO','MANUALE','test',0
          FROM tpo.clienti WHERE public_id='CLI-000001';
          INSERT INTO tpo.righe_ordine
            (public_id,ordine_id,posizione,varieta_id,quantita,unita_misura,version)
          SELECT 'RO-000002',o.id,1,v.id,1,'SET',0
          FROM tpo.ordini o CROSS JOIN tpo.varieta v
          WHERE o.public_id='ORD-000002' AND v.public_id='VAR-000001';
        """)
    run = ProductionPlanningRunSnapshot(PublicId("RPP-000001"), 0, "OPEN")
    base = write_set(run)
    demand1 = base.input_snapshot.demands[0]
    demand2 = replace(
        demand1, order_public_id=PublicId("ORD-000002"),
        order_line_public_id=PublicId("RO-000002"),
        delivery_date=type(demand1.delivery_date)(2026, 8, 16),
    )
    candidate2 = replace(base.revisions[0].lines[0].candidate, demand=demand2)
    line2 = replace(
        base.revisions[0].lines[0], public_id=PublicId("RPS-000002"),
        candidate=candidate2,
        planning_key=type(base.revisions[0].request_key)("d" * 64),
    )
    revision2 = replace(
        base.revisions[0], plan_public_id=PublicId("PP-000002"),
        revision_public_id=PublicId("RVP-000002"),
        request_key=type(base.revisions[0].request_key)("e" * 64), lines=(line2,),
    )
    seed2 = replace(base.seed_resources[0], planning_line_public_id=line2.public_id)
    audit2 = replace(base.audits[0], entity_public_id=revision2.plan_public_id)
    value = replace(
        base,
        input_snapshot=replace(base.input_snapshot, demands=(demand1, demand2)),
        revisions=(*base.revisions, revision2),
        seed_resources=(*base.seed_resources, seed2),
        counters=replace(base.counters, orders_read=2, order_lines_evaluated=2,
                         planning_lines_generated=2),
        audits=tuple(sorted((*base.audits, audit2), key=lambda item: (
            item.entity_type, item.entity_public_id.value, item.operation,
        ))),
    )
    result = PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(value, completed_at=PERSISTENCE_AT)
    assert tuple(item.value for item in result.plan_public_ids) == ("PP-000001", "PP-000002")
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql("SELECT state FROM tpo.production_planning_runs").scalar_one() == "COMMITTED"


def test_deferred_constraint_failure_rolls_back_everything(writer_database) -> None:
    with writer_database.begin() as conn:
        conn.exec_driver_sql("""
          CREATE FUNCTION tpo.test_reject_plan_deferred() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN RAISE EXCEPTION 'test deferred rejection'; END; $$;
          CREATE CONSTRAINT TRIGGER test_reject_plan_deferred
          AFTER INSERT ON tpo.piani_produzione DEFERRABLE INITIALLY DEFERRED
          FOR EACH ROW EXECUTE FUNCTION tpo.test_reject_plan_deferred();
        """)
    with pytest.raises(ProductionPlanningError) as captured:
        _commit(writer_database)
    assert captured.value.category in {"CONCURRENCY_CONFLICT", "COMMIT_FAILED_ROLLED_BACK"}
    _assert_zero_partial_writes(writer_database)


def test_allocation_transition_epoch_compatible_replay(writer_database) -> None:
    transition = allocation_transition()
    value = _transition_write_set(writer_database, transition)
    writer = PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database))
    writer.commit(value, completed_at=PERSISTENCE_AT)
    with writer_database.connect() as conn:
        before = conn.exec_driver_sql(
            "SELECT state,version FROM tpo.allocazioni WHERE public_id='ALL-000001'"
        ).one()
        transition_count = conn.exec_driver_sql(
            "SELECT count(*) FROM tpo.transizioni_allocazione"
        ).scalar_one()
        allocation_audit_count = conn.exec_driver_sql(
            "SELECT count(*) FROM tpo.audit_eventi WHERE entity_public_id='ALL-000001'"
        ).scalar_one()
    run = _open_run(writer_database, 3)
    replay = replace(value, run=run)
    result = writer.commit(replay, completed_at=PERSISTENCE_AT)
    assert result.run_state == "COMMITTED"
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql(
            "SELECT count(*) FROM tpo.transizioni_allocazione"
        ).scalar_one() == transition_count == 1
        assert conn.exec_driver_sql(
            "SELECT state,version FROM tpo.allocazioni WHERE public_id='ALL-000001'"
        ).one() == before == ("ATTIVA", 1)
        assert conn.exec_driver_sql(
            "SELECT count(*) FROM tpo.audit_eventi WHERE entity_public_id='ALL-000001'"
        ).scalar_one() == allocation_audit_count
        assert conn.exec_driver_sql("SELECT 1").scalar_one() == 1


def test_allocation_transition_epoch_incompatible_replay(writer_database) -> None:
    transition = allocation_transition()
    value = _transition_write_set(writer_database, transition)
    writer = PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database))
    writer.commit(value, completed_at=PERSISTENCE_AT)
    run = _open_run(writer_database, 3)
    incompatible = allocation_transition(consumed_quantity_delta="0.5")
    replay = replace(value, run=run, allocation_transitions=(incompatible,))
    with pytest.raises(ProductionPlanningError) as captured:
        writer.commit(replay, completed_at=PERSISTENCE_AT)
    assert captured.value.category == "ALLOCATION_CONFLICT"


def test_allocation_transfer_epoch_replay_reuses_replacement(writer_database) -> None:
    transition = allocation_transition(
        consumed_quantity_delta="0.4", transferred_quantity_delta="0.6",
        target_state="SOSTITUITA",
        replacement_allocation_public_id=PublicId("ALL-000002"),
    )
    replacement = AllocationDraft(
        PublicId("ALL-000002"), "DOMANDA", PublicId("RPS-000001"),
        PublicId("RO-000001"), PublicId("RO-000001"), qty("0.6"),
    )
    value = _transition_write_set(
        writer_database, transition, replacement=replacement
    )
    writer = PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database))
    writer.commit(value, completed_at=PERSISTENCE_AT)
    with writer_database.connect() as conn:
        replacement_before = conn.exec_driver_sql(
            """SELECT a.id,a.quantity,a.unita_misura,a.state,a.version,
                      source.public_id,destination.public_id
               FROM tpo.allocazioni a
               JOIN tpo.allocazioni_domanda child ON child.allocation_id=a.id
               JOIN tpo.righe_ordine source ON source.id=child.riga_ordine_id
               JOIN tpo.righe_piano_semina line ON line.id=a.riga_piano_semina_id
               JOIN tpo.righe_ordine destination ON destination.id=line.riga_ordine_id
               WHERE a.public_id='ALL-000002'"""
        ).one()
        allocation_audits_before = conn.exec_driver_sql(
            "SELECT count(*) FROM tpo.audit_eventi WHERE entity_public_id='ALL-000002'"
        ).scalar_one()
    replay = replace(value, run=_open_run(writer_database, 3))
    assert writer.commit(replay, completed_at=PERSISTENCE_AT).run_state == "COMMITTED"
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql(
            "SELECT state,version FROM tpo.allocazioni WHERE public_id='ALL-000001'"
        ).one() == ("SOSTITUITA", 1)
        assert conn.exec_driver_sql(
            "SELECT count(*) FROM tpo.allocazioni WHERE public_id='ALL-000002'"
        ).scalar_one() == 1
        assert conn.exec_driver_sql(
            "SELECT count(*) FROM tpo.allocazioni_domanda WHERE allocation_id=%s",
            (replacement_before[0],),
        ).scalar_one() == 1
        assert conn.exec_driver_sql(
            """SELECT a.id,a.quantity,a.unita_misura,a.state,a.version,
                      source.public_id,destination.public_id
               FROM tpo.allocazioni a
               JOIN tpo.allocazioni_domanda child ON child.allocation_id=a.id
               JOIN tpo.righe_ordine source ON source.id=child.riga_ordine_id
               JOIN tpo.righe_piano_semina line ON line.id=a.riga_piano_semina_id
               JOIN tpo.righe_ordine destination ON destination.id=line.riga_ordine_id
               WHERE a.public_id='ALL-000002'"""
        ).one() == replacement_before == (
            replacement_before[0], Decimal("0.6"), "SET", "ATTIVA", 0,
            "RO-000001", "RO-000001",
        )
        assert conn.exec_driver_sql(
            """SELECT count(*) FROM tpo.transizioni_allocazione
               WHERE transition_type='SOSTITUITA'"""
        ).scalar_one() == 1
        assert conn.exec_driver_sql(
            "SELECT count(*) FROM tpo.audit_eventi WHERE entity_public_id='ALL-000002'"
        ).scalar_one() == allocation_audits_before
        assert conn.exec_driver_sql("SELECT 1").scalar_one() == 1


def test_same_allocation_epoch_same_payload_concurrency_reuses_winner(
    writer_database,
) -> None:
    import concurrent.futures
    import threading

    transition = allocation_transition()
    value2 = _transition_write_set(writer_database, transition)
    value3 = replace(value2, run=_open_run(writer_database, 3))
    barrier = threading.Barrier(2)

    def execute(value):
        barrier.wait(timeout=10)
        try:
            return PostgreSQLProductionPlanningCommitWriter(_Factory(writer_database)).commit(
                value, completed_at=PERSISTENCE_AT
            ).run_state
        except ProductionPlanningError as error:
            return error.category

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(execute, (value2, value3)))
    assert outcomes == ("COMMITTED", "COMMITTED")
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.transizioni_allocazione").scalar_one() == 1
        assert conn.exec_driver_sql(
            "SELECT state,version FROM tpo.allocazioni WHERE public_id='ALL-000001'"
        ).one() == ("ATTIVA", 1)
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.allocazioni").scalar_one() == 1
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.allocazioni_domanda").scalar_one() == 1
        assert conn.exec_driver_sql(
            "SELECT count(*) FROM tpo.audit_eventi WHERE entity_public_id='ALL-000001'"
        ).scalar_one() == 0
    with writer_database.connect() as first, writer_database.connect() as second:
        assert first.exec_driver_sql("SELECT 1").scalar_one() == 1
        assert second.exec_driver_sql("SELECT 1").scalar_one() == 1


def test_same_allocation_epoch_different_payload_concurrency_conflicts(
    writer_database,
) -> None:
    import concurrent.futures
    import threading

    value2 = _transition_write_set(writer_database, allocation_transition())
    value3 = replace(
        value2,
        run=_open_run(writer_database, 3),
        allocation_transitions=(
            allocation_transition(consumed_quantity_delta="0.5"),
        ),
    )
    barrier = threading.Barrier(2)

    def execute(value):
        barrier.wait(timeout=10)
        try:
            return PostgreSQLProductionPlanningCommitWriter(
                _Factory(writer_database)
            ).commit(value, completed_at=PERSISTENCE_AT).run_state
        except ProductionPlanningError as error:
            return error.category

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(execute, (value2, value3)))
    assert outcomes.count("COMMITTED") == 1
    assert outcomes.count("ALLOCATION_CONFLICT") == 1
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql(
            "SELECT count(*) FROM tpo.transizioni_allocazione"
        ).scalar_one() == 1
        assert conn.exec_driver_sql(
            "SELECT state,version FROM tpo.allocazioni WHERE public_id='ALL-000001'"
        ).one() == ("ATTIVA", 1)
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.allocazioni").scalar_one() == 1
        assert conn.exec_driver_sql("SELECT count(*) FROM tpo.allocazioni_domanda").scalar_one() == 1
        assert conn.exec_driver_sql("SELECT 1").scalar_one() == 1


class _CommitThenRaiseConnection:
    def __init__(self, connection) -> None:
        self._connection = connection

    def commit(self):
        self._connection.commit()
        raise psycopg.OperationalError("fault injected after physical commit")

    def __getattr__(self, name):
        return getattr(self._connection, name)


class _CommitThenRaiseFactory(_Factory):
    def connect(self):
        return _CommitThenRaiseConnection(super().connect())


def test_uncertain_commit_outcome_fault_injection(writer_database) -> None:
    run = ProductionPlanningRunSnapshot(PublicId("RPP-000001"), 0, "OPEN")
    writer = PostgreSQLProductionPlanningCommitWriter(_CommitThenRaiseFactory(writer_database))
    with pytest.raises(ProductionPlanningOutcomeUncertain):
        writer.commit(write_set(run), completed_at=PERSISTENCE_AT)
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql("SELECT state FROM tpo.production_planning_runs WHERE public_id='RPP-000001'").scalar_one() == "COMMITTED"


def test_zero_partial_writes_after_policy_failure(writer_database) -> None:
    with writer_database.begin() as conn:
        conn.exec_driver_sql("UPDATE tpo.production_planning_policy_versions SET planning_algorithm_version='changed'")
    with pytest.raises(ProductionPlanningError):
        _commit(writer_database)
    _assert_zero_partial_writes(writer_database)


def test_connection_health_after_expected_constraint_error(writer_database) -> None:
    with writer_database.begin() as conn:
        conn.exec_driver_sql("UPDATE tpo.righe_ordine SET version=9 WHERE public_id='RO-000001'")
    with pytest.raises(ProductionPlanningError):
        _commit(writer_database)
    with writer_database.connect() as conn:
        assert conn.exec_driver_sql("SELECT 1").scalar_one() == 1
