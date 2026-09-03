from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.tpo_core.application.raccolta.errors import (
    RaccoltaCorrectionNetQuantityNegativeError, RaccoltaCorrectionSeminaMismatchError,
    RaccoltaIdempotencyConflictError, RaccoltaOriginalIsCorrectionError,
    RaccoltaOriginalNotFoundError,
)
from src.tpo_core.application.raccolta.models import CorreggiRaccolta, RaccoltaAuthority
from src.tpo_core.domain.identifiers import ActorId, RaccoltaId, SeminaId
from src.tpo_core.domain.quantities import UnitOfMeasure
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql,
)
from tests.integration.postgresql.test_raccolta import (
    BASE, environment, harvest, harvest_environment, ready,
)


def correction(key="fix-1", *, original="RAC-000001", semina="SEM-000001",
               quantity="-0.25", at=None, notes=None):
    return CorreggiRaccolta(
        RaccoltaId(original), SeminaId(semina), Decimal(quantity), UnitOfMeasure.SET,
        at or (BASE + timedelta(hours=1)),
        RaccoltaAuthority(ActorId("owner"), "correct harvest", f"corr-{key}", key),
        notes,
    )


def scalar(engine, sql):
    with engine.connect() as connection:
        return connection.exec_driver_sql(sql).scalar_one()


def _insert_second_semina(engine, public_id="SEM-000002", discriminator="B"):
    with engine.begin() as connection:
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


def test_correction_creates_new_rac_linked_to_original(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    original = writer.record(harvest())
    result = writer.correct(correction())
    assert result.raccolta_id.value == "RAC-000002"
    assert result.original_raccolta_id == original.raccolta_id
    assert result.semina_id == original.semina_id
    assert result.quantity == Decimal("-0.25")
    assert result.net_quantity_after == Decimal("0.25")
    assert result.outcome == "INSERTED"
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT r.quantita,o.public_id FROM tpo.raccolte r "
            "JOIN tpo.raccolte o ON o.id=r.rettifica_raccolta_id "
            "WHERE r.public_id='RAC-000002'"
        ).one()
    assert row == (Decimal("-0.250000"), "RAC-000001")


def test_original_raccolta_remains_unchanged_after_correction(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    writer.record(harvest())
    writer.correct(correction())
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT quantita,rettifica_raccolta_id FROM tpo.raccolte WHERE public_id='RAC-000001'"
        ).one()
    assert row == (Decimal("0.500000"), None)


def test_correction_allowed_regardless_of_semina_state(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    writer.record(harvest())
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE tpo.semine SET stato='CHIUSA',"
            "esito_finale='RACCOLTA_COMPLETA' "
            "WHERE public_id='SEM-000001'"
        )
    result = writer.correct(correction("closed-semina"))
    assert result.outcome == "INSERTED"


def test_original_not_found_fails_closed_without_identity_consumption(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    before = scalar(
        engine, "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='RACCOLTA_ID'"
    )
    with pytest.raises(RaccoltaOriginalNotFoundError):
        writer.correct(correction("missing-original", original="RAC-999999"))
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolte") == 0
    assert scalar(
        engine, "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='RACCOLTA_ID'"
    ) == before


def test_correction_of_correction_is_rejected(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    writer.record(harvest())
    writer.correct(correction("first-fix"))
    with pytest.raises(RaccoltaOriginalIsCorrectionError):
        writer.correct(correction("chained-fix", original="RAC-000002"))
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolte") == 2


def test_semina_mismatch_is_rejected_without_identity_consumption(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    writer.record(harvest())
    _insert_second_semina(engine)
    before = scalar(
        engine, "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='RACCOLTA_ID'"
    )
    with pytest.raises(RaccoltaCorrectionSeminaMismatchError):
        writer.correct(correction("wrong-semina", semina="SEM-000002"))
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolte") == 1
    assert scalar(
        engine, "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='RACCOLTA_ID'"
    ) == before


def test_net_quantity_negative_is_rejected(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    writer.record(harvest())  # RAC-000001, 0.5 SET
    with pytest.raises(RaccoltaCorrectionNetQuantityNegativeError):
        writer.correct(correction("too-much", quantity="-0.75"))
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolte") == 1


def test_net_quantity_can_reach_exactly_zero_annullamento(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    writer.record(harvest())  # 0.5 SET
    result = writer.correct(correction("void", quantity="-0.5"))
    assert result.net_quantity_after == Decimal("0")
    assert scalar(
        engine,
        "SELECT sum(quantita) FROM tpo.raccolte WHERE rettifica_raccolta_id="
        "(SELECT id FROM tpo.raccolte WHERE public_id='RAC-000001') "
        "OR public_id='RAC-000001'",
    ) == Decimal("0.000000")


def test_further_correction_after_zeroing_still_respects_net_floor(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    writer.record(harvest())
    writer.correct(correction("void", quantity="-0.5"))
    with pytest.raises(RaccoltaCorrectionNetQuantityNegativeError):
        writer.correct(correction("over-void", quantity="-0.000001"))


def test_multiple_corrections_accumulate_net_quantity(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    writer.record(harvest())  # 0.5
    first = writer.correct(correction("plus", quantity="0.5"))
    second = writer.correct(correction("minus", quantity="-0.75"))
    assert first.net_quantity_after == Decimal("1")
    assert second.net_quantity_after == Decimal("0.25")


def test_idempotent_replay_and_conflict(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    writer.record(harvest())
    first = writer.correct(correction())
    replay = writer.correct(correction())
    assert replay.outcome == "COMPATIBLE_REPLAY" and replay.raccolta_id == first.raccolta_id
    assert replay.net_quantity_after == first.net_quantity_after
    with pytest.raises(RaccoltaIdempotencyConflictError):
        writer.correct(correction(quantity="-0.1"))
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolte") == 2


def test_concurrent_identical_and_distinct_corrections(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    writer.record(harvest())
    with ThreadPoolExecutor(max_workers=2) as pool:
        identical = list(pool.map(lambda _: writer.correct(correction("same")), range(2)))
    assert {result.raccolta_id.value for result in identical} == {"RAC-000002"}
    assert {result.outcome for result in identical} == {"INSERTED", "COMPATIBLE_REPLAY"}


def test_audit_event_is_recorded_with_original_reference(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    writer.record(harvest())
    writer.correct(correction())
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT operation,entity_public_id,before_data->>'original_public_id' "
            "FROM tpo.audit_eventi WHERE entity_type='RACCOLTA' AND operation='CORRECTION'"
        ).one()
    assert row == ("CORRECTION", "RAC-000002", "RAC-000001")


def test_correction_row_is_covered_by_database_immutability(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    writer.record(harvest())
    writer.correct(correction())
    for statement in (
        "UPDATE tpo.raccolte SET quantita=1 WHERE public_id='RAC-000002'",
        "DELETE FROM tpo.raccolte WHERE public_id='RAC-000002'",
    ):
        with pytest.raises(
            sa.exc.DBAPIError, match="Raccolta physical fact authority is immutable"
        ):
            with engine.begin() as connection:
                connection.exec_driver_sql(statement)


def test_correction_reuses_the_same_public_identity_sequence_as_recording(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    writer.record(harvest())
    result = writer.correct(correction())
    assert result.raccolta_id.value.startswith("RAC-")
    assert scalar(
        engine, "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='RACCOLTA_ID'"
    ) == 3
