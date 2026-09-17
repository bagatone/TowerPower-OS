from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timezone
from decimal import Decimal
import uuid

from alembic import command as alembic_command
import pytest
import sqlalchemy as sa

from src.tpo_core.application.identity import (
    CommissionIdentityRegistration, IdentityRegistrationCommissioningService,
)
from src.tpo_core.application.onboarding import (
    CommissionCustomer, CommissionSupplyProgram, CommissionVariety, OnboardingAuthority,
)
from src.tpo_core.application.programma_fornitura_sospensione.errors import (
    ProgrammaFornituraClienteGiaAttivoError, ProgrammaFornituraIdempotencyConflictError,
    ProgrammaFornituraNotFoundError, ProgrammaFornituraStateIneligibleError,
    ProgrammaFornituraTimestampRegressionError, ProgrammaFornituraVersionConflictError,
)
from src.tpo_core.application.programma_fornitura_sospensione.models import (
    ProgrammaFornituraSospensioneAuthority, RiattivaProgrammaFornitura,
    SospendiProgrammaFornitura,
)
from src.tpo_core.domain.entities.programma_fornitura import (
    ConfigurazioneTemporale, ProgrammaFornitura, RigaProgrammaFornitura, TipoRicorrenza,
)
from src.tpo_core.domain.entities.varieta import Varieta
from src.tpo_core.domain.identifiers import ActorId, ClienteId, ProgrammaFornituraId, VarietaId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import ProgrammaFornituraState, VarietaState
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.identity_commissioning import (
    PostgreSQLIdentityRegistrationCommissioningWriter,
)
from src.tpo_core.infrastructure.postgresql.onboarding import PostgreSQLOperationalDataOnboardingWriter
from src.tpo_core.infrastructure.postgresql.programma_fornitura_sospensione import (
    PostgreSQLProgrammaFornituraSospensioneWriter,
)
from tests.infrastructure.postgresql.test_production_planning_migrations import isolated_postgresql
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory

ONBOARD_AUTH = OnboardingAuthority(ActorId("tpo.owner"), "Onboarding di test", "onboarding:test:1")
PROGRAM_EFFECTIVE = datetime(2026, 8, 23, tzinfo=timezone.utc)
SOSPENDI_AT = datetime(2026, 8, 24, tzinfo=timezone.utc)
RIATTIVA_AT = datetime(2026, 8, 25, tzinfo=timezone.utc)


@pytest.fixture
def environment(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_pf_sospensione_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    with engine.begin() as connection:
        alembic_command.upgrade(make_config(connection=connection), "head")
    factory = _Factory(engine)
    identity = IdentityRegistrationCommissioningService(
        PostgreSQLIdentityRegistrationCommissioningWriter(factory)
    )
    for identifier in (ClienteId, VarietaId, ProgrammaFornituraId):
        identity.commission(CommissionIdentityRegistration(
            identifier.sequence_name, identifier, identifier.prefix, ActorId("tpo.identity"),
        ))
    onboarding = PostgreSQLOperationalDataOnboardingWriter(factory)
    try:
        yield engine, onboarding, PostgreSQLProgrammaFornituraSospensioneWriter(factory)
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')


def _line(variety="VAR-000001"):
    return RigaProgrammaFornitura(
        VarietaId(variety), Quantity(Decimal("1.5"), UnitOfMeasure.SET),
        ConfigurazioneTemporale(TipoRicorrenza.GIORNI_SETTIMANA, giorni_settimana=(1, 4)),
    )


def onboard_program(onboarding, *, cliente="CLI-000001", programma="PF-000001",
                     variety="VAR-000001"):
    onboarding.commission_customer(CommissionCustomer(ClienteId(cliente), "Cliente di test", ONBOARD_AUTH))
    onboarding.commission_variety(CommissionVariety(
        Varieta(VarietaId(variety), "Cilantro", VarietaState.ATTIVA), ONBOARD_AUTH,
    ))
    program = ProgrammaFornitura(
        ProgrammaFornituraId(programma), ClienteId(cliente), (_line(variety),),
        date(2026, 8, 24), ProgrammaFornituraState.ATTIVO, 14, None, time(5, 0),
    )
    onboarding.commission_supply_program(
        CommissionSupplyProgram(program, 1, PROGRAM_EFFECTIVE, ONBOARD_AUTH)
    )
    return program


def sospendi(key="susp-1", *, programma="PF-000001", expected=1, effective_at=SOSPENDI_AT,
             data_ripresa_prevista=None):
    return SospendiProgrammaFornitura(
        ProgrammaFornituraId(programma), expected, effective_at,
        ProgrammaFornituraSospensioneAuthority(
            ActorId("tpo.owner"), "sospensione di test", f"corr-{key}", key,
        ),
        data_ripresa_prevista,
    )


def riattiva(key="react-1", *, programma="PF-000001", expected=2, effective_at=RIATTIVA_AT):
    return RiattivaProgrammaFornitura(
        ProgrammaFornituraId(programma), expected, effective_at,
        ProgrammaFornituraSospensioneAuthority(
            ActorId("tpo.owner"), "riattivazione di test", f"corr-{key}", key,
        ),
    )


def scalar(engine, sql):
    with engine.connect() as connection:
        return connection.exec_driver_sql(sql).scalar_one()


def test_sospendi_closes_old_version_and_opens_new_one(environment):
    engine, onboarding, writer = environment
    onboard_program(onboarding)
    result = writer.sospendi(sospendi(data_ripresa_prevista=date(2026, 9, 1)))
    assert result.outcome == "INSERTED"
    assert result.numero_versione_precedente == 1
    assert result.numero_versione == 2
    assert result.stato_precedente == "ATTIVO"
    assert result.stato == "SOSPESO"
    assert result.data_ripresa_prevista == date(2026, 9, 1)
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT numero_versione,stato,valida_dal,valida_al FROM tpo.programmi_fornitura_versioni "
            "ORDER BY numero_versione"
        ).all()
    assert len(rows) == 2
    assert rows[0][0:2] == (1, "ATTIVO") and rows[0][3] is not None
    assert rows[1][0:2] == (2, "SOSPESO") and rows[1][3] is None
    assert scalar(
        engine, "SELECT data_ripresa_prevista FROM tpo.programmi_fornitura WHERE public_id='PF-000001'"
    ) == date(2026, 9, 1)


def test_sospendi_without_data_ripresa_prevista_leaves_it_null(environment):
    engine, onboarding, writer = environment
    onboard_program(onboarding)
    result = writer.sospendi(sospendi())
    assert result.data_ripresa_prevista is None
    assert scalar(
        engine, "SELECT data_ripresa_prevista FROM tpo.programmi_fornitura WHERE public_id='PF-000001'"
    ) is None


def test_riattiva_transitions_back_to_attivo(environment):
    engine, onboarding, writer = environment
    onboard_program(onboarding)
    writer.sospendi(sospendi())
    result = writer.riattiva(riattiva())
    assert result.outcome == "INSERTED"
    assert result.numero_versione_precedente == 2
    assert result.numero_versione == 3
    assert result.stato_precedente == "SOSPESO"
    assert result.stato == "ATTIVO"
    assert scalar(
        engine,
        "SELECT stato FROM tpo.programmi_fornitura_versioni pv "
        "JOIN tpo.programmi_fornitura p ON p.id=pv.programma_fornitura_id "
        "WHERE p.public_id='PF-000001' AND pv.valida_al IS NULL",
    ) == "ATTIVO"


def test_righe_e_giorni_sono_copiati_sulla_nuova_versione(environment):
    engine, onboarding, writer = environment
    onboard_program(onboarding)
    writer.sospendi(sospendi())
    with engine.connect() as connection:
        righe = connection.exec_driver_sql(
            """SELECT rpf.posizione,rpf.varieta_id,rpf.quantita,rpg.giorno_iso
               FROM tpo.righe_programma_fornitura rpf
               JOIN tpo.programmi_fornitura_versioni pv ON pv.id=rpf.programma_versione_id
               JOIN tpo.programmi_fornitura p ON p.id=pv.programma_fornitura_id
               JOIN tpo.righe_programma_giorni rpg ON rpg.riga_programma_id=rpf.id
               WHERE p.public_id='PF-000001' AND pv.numero_versione=2
               ORDER BY rpf.posizione,rpg.giorno_iso"""
        ).all()
    assert [row[3] for row in righe] == [1, 4]
    assert righe[0][2] == Decimal("1.500000")


def test_sospendi_rejects_already_sospeso_program(environment):
    engine, onboarding, writer = environment
    onboard_program(onboarding)
    writer.sospendi(sospendi())
    with pytest.raises(ProgrammaFornituraStateIneligibleError):
        writer.sospendi(sospendi("susp-2", expected=2, effective_at=RIATTIVA_AT))
    assert scalar(engine, "SELECT count(*) FROM tpo.programmi_fornitura_versioni") == 2


def test_riattiva_rejects_attivo_program(environment):
    engine, onboarding, writer = environment
    onboard_program(onboarding)
    with pytest.raises(ProgrammaFornituraStateIneligibleError):
        writer.riattiva(riattiva(expected=1))
    assert scalar(engine, "SELECT count(*) FROM tpo.programmi_fornitura_versioni") == 1


def test_sospendi_version_conflict_is_rejected(environment):
    engine, onboarding, writer = environment
    onboard_program(onboarding)
    with pytest.raises(ProgrammaFornituraVersionConflictError):
        writer.sospendi(sospendi(expected=2))
    assert scalar(engine, "SELECT count(*) FROM tpo.programmi_fornitura_versioni") == 1


def test_sospendi_timestamp_regression_is_rejected(environment):
    engine, onboarding, writer = environment
    onboard_program(onboarding)
    with pytest.raises(ProgrammaFornituraTimestampRegressionError):
        writer.sospendi(sospendi(effective_at=PROGRAM_EFFECTIVE))
    assert scalar(engine, "SELECT count(*) FROM tpo.programmi_fornitura_versioni") == 1


def test_sospendi_not_found_is_rejected(environment):
    _, onboarding, writer = environment
    onboard_program(onboarding)
    with pytest.raises(ProgrammaFornituraNotFoundError):
        writer.sospendi(sospendi(programma="PF-999999"))


def test_idempotent_replay_sospendi(environment):
    engine, onboarding, writer = environment
    onboard_program(onboarding)
    first = writer.sospendi(sospendi(data_ripresa_prevista=date(2026, 9, 1)))
    replay = writer.sospendi(sospendi(data_ripresa_prevista=date(2026, 9, 1)))
    assert replay.outcome == "COMPATIBLE_REPLAY"
    assert replay.numero_versione == first.numero_versione
    assert replay.data_ripresa_prevista == date(2026, 9, 1)
    assert replay.recorded_at == first.recorded_at
    with pytest.raises(ProgrammaFornituraIdempotencyConflictError):
        writer.sospendi(sospendi(data_ripresa_prevista=date(2026, 12, 25)))
    assert scalar(engine, "SELECT count(*) FROM tpo.programmi_fornitura_versioni") == 2


def test_idempotent_replay_survives_a_later_sospendi_overwriting_the_header(environment):
    # data_ripresa_prevista vive sull'header mutabile: una successiva chiamata
    # sospendi (nuovo ciclo, altra idempotency key) puo' sovrascriverlo. Il
    # replay della PRIMA chiamata deve restare quello che fu committed allora,
    # non il valore corrente dell'header.
    engine, onboarding, writer = environment
    onboard_program(onboarding)
    first = writer.sospendi(sospendi("susp-1", data_ripresa_prevista=date(2026, 9, 1)))
    writer.riattiva(riattiva("react-1", expected=2))
    writer.sospendi(sospendi(
        "susp-2", expected=3, effective_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
        data_ripresa_prevista=date(2026, 10, 1),
    ))
    replay = writer.sospendi(sospendi("susp-1", data_ripresa_prevista=date(2026, 9, 1)))
    assert replay.outcome == "COMPATIBLE_REPLAY"
    assert replay.data_ripresa_prevista == date(2026, 9, 1)
    assert replay.numero_versione == first.numero_versione
    assert scalar(
        engine, "SELECT data_ripresa_prevista FROM tpo.programmi_fornitura WHERE public_id='PF-000001'"
    ) == date(2026, 10, 1)


def test_idempotent_replay_riattiva(environment):
    engine, onboarding, writer = environment
    onboard_program(onboarding)
    writer.sospendi(sospendi())
    first = writer.riattiva(riattiva())
    replay = writer.riattiva(riattiva())
    assert replay.outcome == "COMPATIBLE_REPLAY"
    assert replay.numero_versione == first.numero_versione
    assert replay.recorded_at == first.recorded_at
    with pytest.raises(ProgrammaFornituraIdempotencyConflictError):
        writer.riattiva(riattiva(effective_at=datetime(2026, 8, 26, tzinfo=timezone.utc)))
    assert scalar(engine, "SELECT count(*) FROM tpo.programmi_fornitura_versioni") == 3


def test_program_can_be_sospeso_e_riattivato_piu_volte(environment):
    engine, onboarding, writer = environment
    onboard_program(onboarding)
    writer.sospendi(sospendi("susp-1"))
    writer.riattiva(riattiva("react-1", expected=2))
    writer.sospendi(sospendi(
        "susp-2", expected=3, effective_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
    ))
    final = writer.riattiva(riattiva(
        "react-2", expected=4, effective_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
    ))
    assert final.numero_versione == 5
    assert final.stato == "ATTIVO"
    assert scalar(engine, "SELECT count(*) FROM tpo.programmi_fornitura_versioni") == 5


def test_riattiva_rejected_when_client_already_has_another_attivo_program(environment):
    engine, onboarding, writer = environment
    onboard_program(onboarding, cliente="CLI-000001", programma="PF-000001", variety="VAR-000001")
    writer.sospendi(sospendi())
    onboard_program(onboarding, cliente="CLI-000001", programma="PF-000002", variety="VAR-000001")
    with pytest.raises(ProgrammaFornituraClienteGiaAttivoError):
        writer.riattiva(riattiva())
    assert scalar(
        engine,
        "SELECT stato FROM tpo.programmi_fornitura_versioni pv "
        "JOIN tpo.programmi_fornitura p ON p.id=pv.programma_fornitura_id "
        "WHERE p.public_id='PF-000001' AND pv.valida_al IS NULL",
    ) == "SOSPESO"


def test_concurrent_identical_and_distinct_sospendi(environment):
    _, onboarding, writer = environment
    onboard_program(onboarding)
    with ThreadPoolExecutor(max_workers=2) as pool:
        identical = list(pool.map(lambda _: writer.sospendi(sospendi("same")), range(2)))
    assert {result.numero_versione for result in identical} == {2}
    assert {result.outcome for result in identical} == {"INSERTED", "COMPATIBLE_REPLAY"}


def test_audit_event_recorded_for_sospendi_and_riattiva(environment):
    engine, onboarding, writer = environment
    onboard_program(onboarding)
    writer.sospendi(sospendi(data_ripresa_prevista=date(2026, 9, 1)))
    writer.riattiva(riattiva())
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT operation,before_data->>'stato',after_data->>'stato',correlation_id "
            "FROM tpo.audit_eventi WHERE entity_type='PROGRAMMA_FORNITURA' "
            "AND operation='STATE_TRANSITION' ORDER BY occurred_at"
        ).all()
    assert rows == [
        ("STATE_TRANSITION", "ATTIVO", "SOSPESO", "corr-susp-1"),
        ("STATE_TRANSITION", "SOSPESO", "ATTIVO", "corr-react-1"),
    ]


def test_new_version_preserves_data_inizio_data_fine_and_orario(environment):
    engine, onboarding, writer = environment
    onboard_program(onboarding)
    writer.sospendi(sospendi())
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT data_inizio,orario_generazione,finestra_operativa_giorni "
            "FROM tpo.programmi_fornitura_versioni ORDER BY numero_versione"
        ).all()
    assert rows[0] == rows[1]
