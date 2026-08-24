from datetime import date, datetime, time, timezone
from decimal import Decimal
import uuid

from alembic import command as alembic_command
import pytest
import sqlalchemy as sa

from src.tpo_core.application.identity import CommissionIdentityRegistration, IdentityRegistrationCommissioningService
from src.tpo_core.application.onboarding import (CommissionCustomer, CommissionSupplyProgram,
    CommissionVariety, CorrectNeverEffectiveSupplyProgramVersion, OnboardingAuthority)
from src.tpo_core.application.onboarding.errors import OnboardingConflictError
from src.tpo_core.domain.entities.programma_fornitura import ConfigurazioneTemporale, ProgrammaFornitura, RigaProgrammaFornitura, TipoRicorrenza
from src.tpo_core.domain.entities.varieta import Varieta
from src.tpo_core.domain.identifiers import ActorId, ClienteId, ProgrammaFornituraId, VarietaId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import ProgrammaFornituraState, VarietaState
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.identity_commissioning import PostgreSQLIdentityRegistrationCommissioningWriter
from src.tpo_core.infrastructure.postgresql.onboarding import PostgreSQLOperationalDataOnboardingWriter
from src.tpo_core.infrastructure.postgresql.programmi_repository import PostgreSQLVersionedProgrammaFornituraRepository
from tests.infrastructure.postgresql.test_production_planning_migrations import isolated_postgresql
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory


AUTH = OnboardingAuthority(ActorId("tpo.owner"), "First real onboarding", "onboarding:test:1")


@pytest.fixture
def environment(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_onboarding_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    with engine.begin() as connection:
        alembic_command.upgrade(make_config(connection=connection), "head")
    factory = _Factory(engine)
    identity = IdentityRegistrationCommissioningService(PostgreSQLIdentityRegistrationCommissioningWriter(factory))
    for identifier in (ClienteId, VarietaId, ProgrammaFornituraId):
        identity.commission(CommissionIdentityRegistration(identifier.sequence_name, identifier, identifier.prefix, ActorId("tpo.identity")))
    try:
        yield engine, factory, PostgreSQLOperationalDataOnboardingWriter(factory)
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')


def test_atomic_onboarding_replay_conflict_audit_and_scheduling_read(environment):
    engine, factory, writer = environment
    customer = CommissionCustomer(ClienteId("CLI-000001"), "Real Customer", AUTH)
    variety = CommissionVariety(Varieta(VarietaId("VAR-000001"), "Cilantro", VarietaState.ATTIVA), AUTH)
    assert writer.commission_customer(customer).inserted
    assert not writer.commission_customer(customer).inserted
    with pytest.raises(OnboardingConflictError):
        writer.commission_customer(CommissionCustomer(customer.customer_id, "Different", AUTH))
    assert writer.commission_variety(variety).inserted
    assert not writer.commission_variety(variety).inserted
    with pytest.raises(OnboardingConflictError):
        writer.commission_variety(CommissionVariety(Varieta(variety.variety.id, "Other", VarietaState.ATTIVA), AUTH))
    line = RigaProgrammaFornitura(
        variety.variety.id, Quantity(Decimal("1.5"), UnitOfMeasure.SET),
        ConfigurazioneTemporale(TipoRicorrenza.GIORNI_SETTIMANA, giorni_settimana=(1, 4)),
    )
    program = ProgrammaFornitura(ProgrammaFornituraId("PF-000001"), customer.customer_id,
        (line,), date(2026, 8, 24), ProgrammaFornituraState.ATTIVO, 14, None, time(5, 0))
    command = CommissionSupplyProgram(program, 1, datetime(2026, 8, 23, tzinfo=timezone.utc), AUTH)
    assert writer.commission_supply_program(command).inserted
    assert not writer.commission_supply_program(command).inserted
    loaded = PostgreSQLVersionedProgrammaFornituraRepository(factory).list_versioned_for_scheduling()
    assert len(loaded) == 1 and loaded[0].programma == program
    with engine.connect() as connection:
        counts = tuple(connection.exec_driver_sql(f"SELECT count(*) FROM tpo.{table}").scalar_one()
                       for table in ("ordini", "righe_ordine"))
        audit = connection.exec_driver_sql("SELECT entity_type,count(*) FROM tpo.audit_eventi GROUP BY entity_type ORDER BY entity_type").all()
    assert counts == (0, 0)
    assert audit == [("CLIENTE", 1), ("PROGRAMMA_FORNITURA", 1), ("VARIETA", 1)]


def test_missing_customer_and_variety_fail_closed(environment):
    _, _, writer = environment
    line = RigaProgrammaFornitura(VarietaId("VAR-999999"), Quantity(Decimal("1"), UnitOfMeasure.SET), ConfigurazioneTemporale(TipoRicorrenza.SETTIMANALE))
    program = ProgrammaFornitura(ProgrammaFornituraId("PF-999999"), ClienteId("CLI-999999"), (line,), date(2026, 8, 24), ProgrammaFornituraState.ATTIVO, 7)
    with pytest.raises(OnboardingConflictError):
        writer.commission_supply_program(CommissionSupplyProgram(program, 1, datetime.now(timezone.utc), AUTH))


def test_never_effective_correction_preserves_evidence_replay_and_scheduling_read(environment):
    engine, factory, writer = environment
    writer.commission_customer(CommissionCustomer(ClienteId("CLI-000001"), "Real Customer", AUTH))
    writer.commission_variety(CommissionVariety(
        Varieta(VarietaId("VAR-000001"), "Cilantro", VarietaState.ATTIVA), AUTH,
    ))
    line = RigaProgrammaFornitura(
        VarietaId("VAR-000001"), Quantity(Decimal("1.5"), UnitOfMeasure.SET),
        ConfigurazioneTemporale(TipoRicorrenza.GIORNI_SETTIMANA, giorni_settimana=(1,)),
    )
    program = ProgrammaFornitura(
        ProgrammaFornituraId("PF-000001"), ClienteId("CLI-000001"), (line,),
        date(2099, 8, 25), ProgrammaFornituraState.ATTIVO, 14, None, time(5),
    )
    writer.commission_supply_program(CommissionSupplyProgram(
        program, 1, datetime(2099, 8, 25, tzinfo=timezone.utc), AUTH,
    ))
    authority = OnboardingAuthority(
        ActorId("tpo.owner"), "Correct never effective", "correction:PF-000001",
    )
    correction = CorrectNeverEffectiveSupplyProgramVersion(
        program, 1, datetime(2099, 8, 23, tzinfo=timezone.utc), authority,
    )
    assert writer.correct_never_effective_supply_program_version(correction).inserted
    assert not writer.correct_never_effective_supply_program_version(correction).inserted
    with pytest.raises(OnboardingConflictError):
        writer.correct_never_effective_supply_program_version(
            CorrectNeverEffectiveSupplyProgramVersion(
                program, 1, datetime(2099, 8, 22, tzinfo=timezone.utc), authority,
            )
        )
    with engine.connect() as connection:
        versions = connection.exec_driver_sql(
            """SELECT numero_versione,voided_at IS NOT NULL,replacement_version_id IS NOT NULL
               FROM tpo.programmi_fornitura_versioni ORDER BY numero_versione"""
        ).all()
        audits = connection.exec_driver_sql(
            """SELECT operation,after_data->>'category',correlation_id
               FROM tpo.audit_eventi
               WHERE entity_type='PROGRAMMA_FORNITURA_VERSION_CORRECTION'"""
        ).all()
    assert versions == [(1, True, True), (2, False, False)]
    assert audits == [("STATE_TRANSITION", "NEVER_EFFECTIVE", "correction:PF-000001")]
    loaded = PostgreSQLVersionedProgrammaFornituraRepository(factory).list_versioned_for_scheduling()
    assert len(loaded) == 1 and loaded[0].version == 2


def test_effective_never_effective_correction_is_rejected(environment):
    _, _, writer = environment
    writer.commission_customer(CommissionCustomer(ClienteId("CLI-000001"), "Real Customer", AUTH))
    writer.commission_variety(CommissionVariety(
        Varieta(VarietaId("VAR-000001"), "Cilantro", VarietaState.ATTIVA), AUTH,
    ))
    line = RigaProgrammaFornitura(
        VarietaId("VAR-000001"), Quantity(Decimal("1"), UnitOfMeasure.SET),
        ConfigurazioneTemporale(TipoRicorrenza.SETTIMANALE),
    )
    program = ProgrammaFornitura(
        ProgrammaFornituraId("PF-000001"), ClienteId("CLI-000001"), (line,),
        date(2020, 1, 1), ProgrammaFornituraState.ATTIVO, 14,
    )
    writer.commission_supply_program(CommissionSupplyProgram(
        program, 1, datetime(2020, 1, 1, tzinfo=timezone.utc), AUTH,
    ))
    with pytest.raises(OnboardingConflictError, match="temporalmente efficace"):
        writer.correct_never_effective_supply_program_version(
            CorrectNeverEffectiveSupplyProgramVersion(
                program, 1, datetime(2019, 1, 1, tzinfo=timezone.utc), AUTH,
            )
        )
