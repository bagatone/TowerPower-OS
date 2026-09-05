from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.assegnazione_fisica.errors import (
    AssegnazioneFisicaConsegnaNotFoundError,
    AssegnazioneFisicaConsegnaRigaOrdineMismatchError,
    AssegnazioneFisicaIdempotencyConflictError,
    AssegnazioneFisicaRaccoltaNotFoundError,
    AssegnazioneFisicaRigaOrdineNotFoundError,
)
from src.tpo_core.application.assegnazione_fisica.models import (
    AssegnazioneFisicaAuthority, RegistraAssegnazioneFisica,
)
from src.tpo_core.domain.identifiers import ActorId, ConsegnaId, RaccoltaId, RigaOrdineId
from src.tpo_core.infrastructure.postgresql.assegnazione_fisica import (
    PostgreSQLAssegnazioneFisicaWriter,
)
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql,
)
from tests.integration.postgresql.test_raccolta import harvest, harvest_environment, ready
from tests.integration.postgresql.test_semina_commissioning import environment

BASE = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)


def assegnazione(*, raccolta="RAC-000001", riga_ordine="RO-000101", consegna=None,
                  quantita="50.5", uom="GRAM", key="assegna-1", at=BASE,
                  motivo="assegnazione a cliente"):
    return RegistraAssegnazioneFisica(
        raccolta_id=RaccoltaId(raccolta),
        riga_ordine_id=RigaOrdineId(riga_ordine),
        quantita_assegnata=Decimal(quantita),
        unita_misura=uom,
        effective_at=at,
        motivo=motivo,
        authority=AssegnazioneFisicaAuthority(
            ActorId("operatore"), "assegnazione fisica", f"corr-{key}", key,
        ),
        consegna_id=ConsegnaId(consegna) if consegna else None,
    )


def _varieta_pk(engine) -> int:
    with engine.connect() as connection:
        return connection.exec_driver_sql(
            "SELECT id FROM tpo.varieta WHERE public_id='VAR-000001'"
        ).scalar_one()


def _cliente_pk(engine) -> int:
    with engine.begin() as connection:
        row = connection.exec_driver_sql(
            "SELECT id FROM tpo.clienti WHERE public_id='CLI-000001'"
        ).fetchone()
        if row is not None:
            return row[0]
        return connection.exec_driver_sql(
            """INSERT INTO tpo.clienti(public_id,denominazione,created_by,updated_at,updated_by)
               VALUES ('CLI-000001','Cliente test','test',CURRENT_TIMESTAMP,'test')
               RETURNING id"""
        ).scalar_one()


def _ordine_con_riga(engine, *, ordine_public_id="ORD-000101", riga_public_id="RO-000101",
                      quantita=100, stato="APERTO") -> int:
    # ORD-000101/RO-000101 (non ORD-000001/RO-000001): quei public_id sono già
    # seminati da _seed_authorities (test_production_planning_commit_writer.py),
    # riusata dalla catena environment -> harvest_environment di questo modulo.
    cliente_pk = _cliente_pk(engine)
    varieta_pk = _varieta_pk(engine)
    with engine.begin() as connection:
        ordine_pk = connection.exec_driver_sql(
            """INSERT INTO tpo.ordini(public_id,cliente_id,data_ordine,data_consegna_prevista,
                                       stato,tipo_creazione,created_by)
               VALUES (%s,%s,DATE '2026-09-05',DATE '2026-09-06',%s,'MANUALE','test')
               RETURNING id""",
            (ordine_public_id, cliente_pk, stato),
        ).scalar_one()
        connection.exec_driver_sql(
            """INSERT INTO tpo.righe_ordine
               (ordine_id,posizione,varieta_id,quantita,unita_misura,public_id)
               VALUES (%s,1,%s,%s,'GRAM',%s)""",
            (ordine_pk, varieta_pk, quantita, riga_public_id),
        )
    return ordine_pk


def _seconda_riga_ordine(engine, *, ordine_pk: int, riga_public_id="RO-000102",
                          quantita=40, posizione=2) -> None:
    varieta_pk = _varieta_pk(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """INSERT INTO tpo.righe_ordine
               (ordine_id,posizione,varieta_id,quantita,unita_misura,public_id)
               VALUES (%s,%s,%s,%s,'GRAM',%s)""",
            (ordine_pk, posizione, varieta_pk, quantita, riga_public_id),
        )


def _consegna(engine, *, ordine_pk: int, consegna_public_id="CON-000101") -> int:
    # stato='CONSEGNATA' (con data_effettiva valorizzata, ck_consegne_data_effettiva):
    # i test che collegano una CONSEGNA a un ORDINE gia' impostato su
    # PARZIALMENTE_EVASO richiedono che la CONSEGNA risulti gia' effettivamente
    # consegnata, altrimenti il trigger di coerenza ct_ordini_fulfilment_state
    # (fn_check_ordine_fulfilment_state, che conta come "delivered" solo le
    # righe_consegna collegate a una CONSEGNA con stato='CONSEGNATA') si
    # aspetterebbe ancora APERTO.
    with engine.begin() as connection:
        cliente_pk = connection.exec_driver_sql(
            "SELECT cliente_id FROM tpo.ordini WHERE id=%s", (ordine_pk,),
        ).scalar_one()
        consegna_pk = connection.exec_driver_sql(
            """INSERT INTO tpo.consegne(public_id,cliente_id,stato,data_prevista,
                                         data_effettiva,created_by)
               VALUES (%s,%s,'CONSEGNATA',DATE '2026-09-06',%s,'test') RETURNING id""",
            (consegna_public_id, cliente_pk, BASE),
        ).scalar_one()
        connection.exec_driver_sql(
            "INSERT INTO tpo.consegne_ordini(consegna_id,ordine_id,posizione) VALUES (%s,%s,1)",
            (consegna_pk, ordine_pk),
        )
    return consegna_pk


def _riga_consegna(engine, *, consegna_pk: int, ordine_pk: int, riga_public_id: str,
                    quantita=10, posizione=1) -> None:
    varieta_pk = _varieta_pk(engine)
    with engine.connect() as connection:
        riga_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.righe_ordine WHERE public_id=%s", (riga_public_id,),
        ).scalar_one()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """INSERT INTO tpo.righe_consegna
               (consegna_id,ordine_id,riga_ordine_id,posizione,varieta_id,quantita,
                unita_misura,created_at,created_by)
               VALUES (%s,%s,%s,%s,%s,%s,'GRAM',%s,'test')""",
            (consegna_pk, ordine_pk, riga_pk, posizione, varieta_pk, quantita, BASE),
        )


@pytest.fixture
def seeded_assegnazione(harvest_environment):
    engine, raccolta_writer = harvest_environment
    ready(engine)
    raccolta_result = raccolta_writer.record(harvest())
    return engine, raccolta_result


def test_registra_assegnazione_creates_fact(seeded_assegnazione):
    engine, raccolta = seeded_assegnazione
    _ordine_con_riga(engine)
    writer = PostgreSQLAssegnazioneFisicaWriter(_Factory(engine))
    result = writer.registra(assegnazione(raccolta=raccolta.raccolta_id.value))
    assert result.outcome == "INSERTED"
    assert result.consegna_id is None
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT raccolta_id,riga_ordine_id,consegna_id,quantita_assegnata,unita_misura "
            "FROM tpo.assegnazioni_fisiche WHERE public_id=%s",
            (result.assegnazione_fisica_id.value,),
        ).fetchone()
        assert row[2] is None
        assert Decimal(row[3]) == Decimal("50.5")
        assert row[4] == "GRAM"
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='ASSEGNAZIONE_FISICA' "
            "AND entity_public_id=%s AND operation='INSERT'",
            (result.assegnazione_fisica_id.value,),
        ).scalar_one() == 1


def test_registra_assegnazione_with_coherent_consegna(seeded_assegnazione):
    engine, raccolta = seeded_assegnazione
    ordine_pk = _ordine_con_riga(engine, stato="PARZIALMENTE_EVASO")
    consegna_pk = _consegna(engine, ordine_pk=ordine_pk)
    _riga_consegna(engine, consegna_pk=consegna_pk, ordine_pk=ordine_pk,
                    riga_public_id="RO-000101")
    writer = PostgreSQLAssegnazioneFisicaWriter(_Factory(engine))
    result = writer.registra(
        assegnazione(raccolta=raccolta.raccolta_id.value, consegna="CON-000101"),
    )
    assert result.outcome == "INSERTED"
    assert result.consegna_id == ConsegnaId("CON-000101")


def test_rejects_consegna_linked_to_different_riga_ordine(seeded_assegnazione):
    engine, raccolta = seeded_assegnazione
    ordine_pk = _ordine_con_riga(engine, stato="PARZIALMENTE_EVASO")
    _seconda_riga_ordine(engine, ordine_pk=ordine_pk)
    consegna_pk = _consegna(engine, ordine_pk=ordine_pk)
    _riga_consegna(engine, consegna_pk=consegna_pk, ordine_pk=ordine_pk,
                    riga_public_id="RO-000102", quantita=40)
    writer = PostgreSQLAssegnazioneFisicaWriter(_Factory(engine))
    with pytest.raises(AssegnazioneFisicaConsegnaRigaOrdineMismatchError):
        writer.registra(
            assegnazione(raccolta=raccolta.raccolta_id.value, riga_ordine="RO-000101",
                         consegna="CON-000101"),
        )


def test_rejects_unknown_consegna(seeded_assegnazione):
    engine, raccolta = seeded_assegnazione
    _ordine_con_riga(engine)
    writer = PostgreSQLAssegnazioneFisicaWriter(_Factory(engine))
    with pytest.raises(AssegnazioneFisicaConsegnaNotFoundError):
        writer.registra(
            assegnazione(raccolta=raccolta.raccolta_id.value, consegna="CON-999999"),
        )


def test_rejects_unknown_raccolta(seeded_assegnazione):
    engine, _ = seeded_assegnazione
    writer = PostgreSQLAssegnazioneFisicaWriter(_Factory(engine))
    with pytest.raises(AssegnazioneFisicaRaccoltaNotFoundError):
        writer.registra(assegnazione(raccolta="RAC-999999"))


def test_rejects_unknown_riga_ordine(seeded_assegnazione):
    engine, raccolta = seeded_assegnazione
    writer = PostgreSQLAssegnazioneFisicaWriter(_Factory(engine))
    with pytest.raises(AssegnazioneFisicaRigaOrdineNotFoundError):
        writer.registra(
            assegnazione(raccolta=raccolta.raccolta_id.value, riga_ordine="RO-999999"),
        )


def test_idempotent_replay_returns_same_assegnazione(seeded_assegnazione):
    engine, raccolta = seeded_assegnazione
    _ordine_con_riga(engine)
    writer = PostgreSQLAssegnazioneFisicaWriter(_Factory(engine))
    first = writer.registra(
        assegnazione(raccolta=raccolta.raccolta_id.value, key="shared-key"),
    )
    replay = writer.registra(
        assegnazione(raccolta=raccolta.raccolta_id.value, key="shared-key"),
    )
    assert replay.outcome == "COMPATIBLE_REPLAY"
    assert replay.assegnazione_fisica_id == first.assegnazione_fisica_id


def test_rejects_idempotency_key_reused_with_different_payload(seeded_assegnazione):
    engine, raccolta = seeded_assegnazione
    _ordine_con_riga(engine)
    writer = PostgreSQLAssegnazioneFisicaWriter(_Factory(engine))
    writer.registra(assegnazione(raccolta=raccolta.raccolta_id.value, key="conflict-key"))
    with pytest.raises(AssegnazioneFisicaIdempotencyConflictError):
        writer.registra(
            assegnazione(raccolta=raccolta.raccolta_id.value, key="conflict-key",
                         quantita="999"),
        )
