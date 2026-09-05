from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.tpo_core.application.fattura_rettifica import (
    FatturaRettificaIdempotencyConflictError,
    FatturaRettificaValidationError,
    RectifyFattura,
    RectifyFatturaAuthority,
    RettificaRigaFattura,
)
from src.tpo_core.domain.identifiers import ActorId, NumeroFattura
from src.tpo_core.infrastructure.postgresql.fattura_rettifica import (
    PostgreSQLFatturaRettificaWriter,
)
from tests.infrastructure.postgresql.test_fattura_emissione_writer import (
    _command as _emissione_command,
    _seed,
    _writer as _emissione_writer,
    fattura_postgresql_cluster_engine,
    fattura_postgresql_engine,
)
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql as migration_postgresql,
)


def _rettifica_writer(engine) -> PostgreSQLFatturaRettificaWriter:
    from tests.infrastructure.postgresql.test_fattura_emissione_writer import _Factory
    return PostgreSQLFatturaRettificaWriter(_Factory(engine))


def _rettifica_command(rettifica_di: str, *, righe=None, data_emissione: date = date(2026, 9, 5),
                        idempotency_key: str = "rettifica-key") -> RectifyFattura:
    return RectifyFattura(
        rettifica_di=NumeroFattura(rettifica_di),
        righe=righe or (RettificaRigaFattura(posizione_originale=1, quantita=Decimal("-1")),),
        data_emissione=data_emissione,
        authority=RectifyFatturaAuthority(
            ActorId("fattura-rettifica-test"), "correzione test", "corr-rettifica", idempotency_key,
        ),
    )


def _emit_seeded_fattura(engine, number: int, *, consegne: int = 1,
                         quantity: str = "2", prezzo_unitario: str = "5.0000",
                         aliquota_igic: str = "7.00"):
    _seed(engine, number, consegne=consegne, quantity=quantity,
          prezzo_unitario=prezzo_unitario, aliquota_igic=aliquota_igic)
    return _emissione_writer(engine).emit(_emissione_command(number, consegne=consegne))


def test_real_postgresql_rectifies_single_riga_with_correct_totals_and_new_numero(
    fattura_postgresql_engine,
) -> None:
    engine = fattura_postgresql_engine
    emitted = _emit_seeded_fattura(engine, 940001)
    writer = _rettifica_writer(engine)
    result = writer.rectify(_rettifica_command(emitted.numero_fattura.value))
    assert result.outcome == "INSERTED"
    assert result.numero_fattura != emitted.numero_fattura
    assert result.rettifica_di == emitted.numero_fattura
    assert result.totale_netto == Decimal("-5.00")
    assert result.totale_igic == Decimal("-0.35")
    assert result.totale == Decimal("-5.35")
    assert result.riga_count == 1
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT rettifica_di FROM tpo.fatture WHERE numero_fattura=%s",
            (result.numero_fattura.value,),
        ).scalar_one() == emitted.numero_fattura.value
        row = connection.exec_driver_sql(
            "SELECT riga_consegna_id,rettifica_riga_fattura_id,quantita "
            "FROM tpo.righe_fattura WHERE fattura_id=%s",
            (result.fattura_id,),
        ).fetchone()
        assert row[0] is None
        assert row[1] is not None
        assert Decimal(row[2]) == Decimal("-1")
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='FATTURA' "
            "AND entity_public_id=%s AND operation='CORRECTION'",
            (result.numero_fattura.value,),
        ).scalar_one() == 1


def test_real_postgresql_multi_riga_rectification_sums_totals(fattura_postgresql_engine) -> None:
    engine = fattura_postgresql_engine
    emitted = _emit_seeded_fattura(engine, 940101, consegne=2)
    writer = _rettifica_writer(engine)
    result = writer.rectify(_rettifica_command(
        emitted.numero_fattura.value,
        righe=(
            RettificaRigaFattura(posizione_originale=1, quantita=Decimal("-1")),
            RettificaRigaFattura(posizione_originale=2, quantita=Decimal("-2")),
        ),
    ))
    assert result.riga_count == 2
    assert result.totale_netto == Decimal("-15.00")
    assert result.totale_igic == Decimal("-1.05")
    assert result.totale == Decimal("-16.05")


def test_real_postgresql_idempotent_replay_returns_same_numero_without_reallocating(
    fattura_postgresql_engine,
) -> None:
    engine = fattura_postgresql_engine
    emitted = _emit_seeded_fattura(engine, 940201)
    writer = _rettifica_writer(engine)
    first = writer.rectify(_rettifica_command(emitted.numero_fattura.value, idempotency_key="shared-key"))
    replay = writer.rectify(_rettifica_command(emitted.numero_fattura.value, idempotency_key="shared-key"))
    assert replay.outcome == "COMPATIBLE_REPLAY"
    assert replay.numero_fattura == first.numero_fattura


def test_real_postgresql_rejects_idempotency_key_reused_with_different_payload(
    fattura_postgresql_engine,
) -> None:
    engine = fattura_postgresql_engine
    emitted = _emit_seeded_fattura(engine, 940301)
    writer = _rettifica_writer(engine)
    writer.rectify(_rettifica_command(emitted.numero_fattura.value, idempotency_key="conflict-key"))
    with pytest.raises(FatturaRettificaIdempotencyConflictError):
        writer.rectify(_rettifica_command(
            emitted.numero_fattura.value, idempotency_key="conflict-key",
            righe=(RettificaRigaFattura(posizione_originale=1, quantita=Decimal("-1.5")),),
        ))


def test_real_postgresql_rejects_already_rectified_riga(fattura_postgresql_engine) -> None:
    engine = fattura_postgresql_engine
    emitted = _emit_seeded_fattura(engine, 940401)
    writer = _rettifica_writer(engine)
    writer.rectify(_rettifica_command(emitted.numero_fattura.value, idempotency_key="first-key"))
    with pytest.raises(FatturaRettificaValidationError):
        writer.rectify(_rettifica_command(emitted.numero_fattura.value, idempotency_key="second-key"))


def test_real_postgresql_rejects_unknown_original_fattura(fattura_postgresql_engine) -> None:
    engine = fattura_postgresql_engine
    writer = _rettifica_writer(engine)
    with pytest.raises(FatturaRettificaValidationError):
        writer.rectify(_rettifica_command("2099/9999"))


def test_real_postgresql_rejects_unknown_posizione(fattura_postgresql_engine) -> None:
    engine = fattura_postgresql_engine
    emitted = _emit_seeded_fattura(engine, 940501)
    writer = _rettifica_writer(engine)
    with pytest.raises(FatturaRettificaValidationError):
        writer.rectify(_rettifica_command(
            emitted.numero_fattura.value,
            righe=(RettificaRigaFattura(posizione_originale=99, quantita=Decimal("-1")),),
        ))


def test_real_postgresql_rejects_rectifying_a_rectification(fattura_postgresql_engine) -> None:
    engine = fattura_postgresql_engine
    emitted = _emit_seeded_fattura(engine, 940601)
    writer = _rettifica_writer(engine)
    first = writer.rectify(_rettifica_command(emitted.numero_fattura.value, idempotency_key="first-key"))
    with pytest.raises(FatturaRettificaValidationError):
        writer.rectify(_rettifica_command(first.numero_fattura.value, idempotency_key="second-key"))
