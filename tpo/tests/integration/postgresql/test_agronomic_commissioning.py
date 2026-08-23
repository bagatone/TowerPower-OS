from dataclasses import replace
from datetime import date, datetime, time, timezone
from decimal import Decimal

from alembic import command as alembic_command
import pytest

from src.tpo_core.application.agronomic_commissioning.errors import AgronomicCommissioningConflictError
from src.tpo_core.application.agronomic_commissioning.models import CommissionAgronomicProtocolCommand
from src.tpo_core.application.agronomic_commissioning.service import AgronomicProtocolCommissioningService
from src.tpo_core.domain.identifiers import ActorId, ProtocolloVersioneId, VarietaId
from src.tpo_core.domain.time_reference import CurrentSystemDate
from src.tpo_core.infrastructure.postgresql.agronomic_commissioning import PostgreSQLAgronomicProtocolCommissioningWriter
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_production_planning_migrations import isolated_postgresql


NOW = datetime(2026, 8, 23, 12, tzinfo=timezone.utc)


class Clock:
    def now(self): return CurrentSystemDate(NOW)


def command():
    return CommissionAgronomicProtocolCommand(
        VarietaId("VAR-000001"), "Afila", "Afila", "MICROGREEN", "Microgreens",
        "Tower Power standard Afila", ProtocolloVersioneId("PV-000001"), 1,
        date(2026, 8, 1), None, Decimal("12"), time(6), time(6), 5, 5,
        Decimal("32"), Decimal("1"), Decimal("0.5"), 1, 1, 0,
        "hydration=12; germination=5; light=5; seed=32; usable_after_ready=5; observational metadata only, not mapped to V1 harvest lead",
        "Initial Tower Power real agronomic protocol commissioning for Production Planning V1.",
        None, "OWNER_AUTHORIZED_REAL_GROWING_PROTOCOL_2026-08", ActorId("tpo.owner"),
        "Initial real agronomic protocol commissioning", "real-agronomic-protocol-v1:afila",
    )


def test_atomic_insert_replay_audit_conflict_and_input_shape(isolated_postgresql):
    with isolated_postgresql.engine.begin() as connection:
        alembic_command.upgrade(make_config(connection=connection), "head")
        connection.exec_driver_sql("""INSERT INTO tpo.varieta
            (public_id,denominazione,stato,created_by,updated_at,updated_by,version)
            VALUES ('VAR-000001','Afila','ATTIVA','tpo.owner',CURRENT_TIMESTAMP,'tpo.owner',0)""")
    service = AgronomicProtocolCommissioningService(
        writer=PostgreSQLAgronomicProtocolCommissioningWriter(_Factory(isolated_postgresql.engine)),
        clock=Clock(),
    )
    first = service.commission(command())
    replay = service.commission(command())
    assert first.inserted_entities == ("USO_PRODUTTIVO", "CULTIVAR", "CULTIVAR_USO", "PROTOCOLLO", "PROTOCOLLO_VERSIONE")
    assert replay.inserted_entities == () and replay.approved_at == first.approved_at
    with isolated_postgresql.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM tpo.protocollo_versioni").scalar_one() == 1
        row = connection.exec_driver_sql("""SELECT stato_approvazione,germinazione_giorni,
            crescita_luce_giorni,ciclo_produttivo_nominale_giorni,grammi_seme_per_set,
            resa_attesa,resa_unita_misura,granularita_produttiva,harvest_min_lead_giorni,
            harvest_max_lead_giorni,provenance FROM tpo.protocollo_versioni""").one()
        assert tuple(row) == ("APPROVATA", 5, 5, 10, Decimal("32"), Decimal("1"), "SET", Decimal("0.5"), 1, 1, "OWNER_AUTHORIZED_REAL_GROWING_PROTOCOL_2026-08")
        assert connection.exec_driver_sql("SELECT count(*) FROM tpo.audit_eventi").scalar_one() == 1
    with pytest.raises(AgronomicCommissioningConflictError):
        service.commission(replace(command(), seed_grams_per_set=Decimal("31")))
