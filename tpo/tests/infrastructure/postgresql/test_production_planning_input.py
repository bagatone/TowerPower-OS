"""Fail-closed helpers and frozen SQL contract for the Planning input loader."""

from decimal import Decimal
import inspect

import pytest

from src.tpo_core.application.production_planning.errors import ProductionPlanningError
from src.tpo_core.infrastructure.postgresql.production_planning_input import (
    PostgreSQLProductionPlanningInputAdapter, _balance,
)
from tests.infrastructure.postgresql.test_production_planning_commit_writer import (
    migration_postgresql, writer_cluster,
    writer_database as planning_input_database,
)


def test_resource_balance_rejects_negative_residual_and_uom_mismatch():
    with pytest.raises(ProductionPlanningError) as overallocated:
        _balance(Decimal("1"), "SET", Decimal("1.1"), "SET")
    assert overallocated.value.category == "ALLOCATION_CONFLICT"
    with pytest.raises(ProductionPlanningError) as mismatch:
        _balance(Decimal("1"), "SET", Decimal("0.1"), "GRAM")
    assert mismatch.value.code == "RESOURCE_UOM_MISMATCH"


def test_loader_uses_one_read_only_repeatable_read_transaction():
    source = inspect.getsource(PostgreSQLProductionPlanningInputAdapter.load)
    assert "REPEATABLE READ READ ONLY" in source
    assert source.count("self._connection_factory.connect()") == 1
    assert source.count("connection.commit()") == 1


def test_stock_has_no_readiness_and_semina_reads_0015_authority_directly():
    source = inspect.getsource(PostgreSQLProductionPlanningInputAdapter)
    stock_method = inspect.getsource(PostgreSQLProductionPlanningInputAdapter._stock)
    semina_method = inspect.getsource(PostgreSQLProductionPlanningInputAdapter._in_progress)
    assert "readiness" not in stock_method.lower()
    for field in ("expected_useful_quantity", "expected_useful_uom",
                  "harvest_window_start", "harvest_window_end"):
        assert field in semina_method
    assert "data_avvio" not in semina_method and "protocol fallback" not in source.lower()


def test_all_semantic_queries_have_explicit_deterministic_ordering():
    for method_name in (
        "_demands", "_knowledge", "_allocations", "_stock", "_in_progress",
        "_harvests", "_current_plans", "_current_lines", "_dispositions",
    ):
        source = inspect.getsource(getattr(PostgreSQLProductionPlanningInputAdapter, method_name))
        assert "ORDER BY" in source


def test_current_lines_executes_against_schema_migrated_to_0015(
    planning_input_database,
):
    with planning_input_database.connect() as connection:
        with connection.connection.cursor() as cursor:
            assert PostgreSQLProductionPlanningInputAdapter._current_lines(cursor) == ()


def _seed_harvest(engine, number: int, quantity: str, loaded: str | None) -> None:
    """SEMINA + RACCOLTA (SET) + eventuale CARICO a magazzino per la varieta' del fixture."""
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        variety_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.varieta WHERE public_id='VAR-000001'").scalar_one()
        semina_pk = connection.exec_driver_sql("""
          INSERT INTO tpo.semine
            (public_id,varieta_id,cultivar_id,cultivar_uso_id,lotto_seme_id,
             protocollo_versione_id,stato,quantita_seme,unita_misura,data_avvio,
             causa_origine,cultivar_snapshot,uso_produttivo_snapshot,
             lotto_seme_snapshot,protocollo_snapshot,created_by,codice_tracciabilita)
          VALUES (%s,%s,1,1,1,1,'PRONTA_ALLA_RACCOLTA',10,'GRAM',TIMESTAMPTZ '2026-09-01 08:00+00',
                  'PIANO_PRODUZIONE','x','x','x','x','harvest-test',%s) RETURNING id
        """, (f"SEM-{number:06d}", variety_pk, f"AFI-0109-{chr(64 + number)}")).scalar_one()
        raccolta_pk = connection.exec_driver_sql("""
          INSERT INTO tpo.raccolte(public_id,semina_id,data_raccolta,quantita,unita_misura,created_by)
          VALUES (%s,%s,TIMESTAMPTZ '2026-09-20 08:00+00',%s,'SET','harvest-test') RETURNING id
        """, (f"RAC-{number:06d}", semina_pk, quantity)).scalar_one()
        if loaded is not None:
            connection.exec_driver_sql("""
              INSERT INTO tpo.movimenti_magazzino
                (public_id,varieta_id,unita_misura,tipo,direzione,quantita,data_movimento,
                 motivo,origine_tipo,raccolta_id,created_at,created_by)
              VALUES (%s,%s,'SET','CARICO','POSITIVO',%s,TIMESTAMPTZ '2026-09-20 09:00+00',
                      'carico da raccolta','RACCOLTA',%s,TIMESTAMPTZ '2026-09-20 09:00+00','harvest-test')
            """, (f"MOV-{number:06d}", variety_pk, loaded, raccolta_pk))


def _harvests(engine, balances=None):
    with engine.connect() as connection:
        with connection.connection.cursor() as cursor:
            return {
                h.harvest_public_id.value: h
                for h in PostgreSQLProductionPlanningInputAdapter._harvests(cursor, balances or {})
            }


def test_harvest_loaded_to_stock_is_not_offered_again_as_harvest(planning_input_database):
    _seed_harvest(planning_input_database, 1, "2", None)    # mai caricata: tutta eleggibile
    _seed_harvest(planning_input_database, 2, "2", "2")     # caricata per intero: 0 residuo
    _seed_harvest(planning_input_database, 3, "2", "0.5")   # caricata in parte: 1.5 residuo
    result = _harvests(planning_input_database)
    assert (result["RAC-000001"].eligible.value, result["RAC-000001"].allocable_residual.value) == (
        Decimal("2"), Decimal("2"))
    assert result["RAC-000001"].provenance == "tpo.raccolte"
    assert result["RAC-000002"].allocable_residual.value == Decimal("0")
    assert result["RAC-000002"].provenance == "tpo.raccolte-meno-carichi-magazzino"
    assert (result["RAC-000003"].eligible.value, result["RAC-000003"].allocable_residual.value) == (
        Decimal("1.5"), Decimal("1.5"))


def test_existing_harvest_allocations_stay_valid_even_if_loaded(planning_input_database):
    _seed_harvest(planning_input_database, 1, "2", "2")
    _seed_harvest(planning_input_database, 2, "1", "1")
    balances = {("RACCOLTA", "RAC-000001"): (Decimal("2"), "SET"),
                ("RACCOLTA", "RAC-000002"): (Decimal("0.4"), "SET")}
    result = _harvests(planning_input_database, balances)
    assert result["RAC-000001"].eligible.value == Decimal("2")       # mai sotto l'allocato
    assert result["RAC-000001"].allocable_residual.value == Decimal("0")
    assert result["RAC-000002"].eligible.value == Decimal("0.4")
    assert result["RAC-000002"].allocable_residual.value == Decimal("0")


def test_harvests_query_ignores_loads_in_other_unit():
    source = inspect.getsource(PostgreSQLProductionPlanningInputAdapter._harvests)
    assert "m.unita_misura=r.unita_misura" in source and "ORDER BY" in source


class _StockCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *_args, **_kwargs):
        return None

    def fetchall(self):
        return self._rows


def _stock(rows):
    return PostgreSQLProductionPlanningInputAdapter._stock(_StockCursor(rows), {})


def test_stock_all_rows_zero_is_represented_by_the_set_row():
    # Regressione 5/10/2026: Afila con riga GRAM congelata a 0 e riga SET venduta fuori sistema (0)
    # faceva fallire il planner con STOCK_RESOURCE_CONFLICT.
    (snapshot,) = _stock([("VAR-000001", Decimal("0"), "GRAM", 3), ("VAR-000001", Decimal("0"), "SET", 7)])
    assert snapshot.eligible.unit.value == "SET" and snapshot.eligible.value == 0


def test_stock_prefers_the_single_live_row_and_still_fails_closed_when_ambiguous():
    (snapshot,) = _stock([("VAR-000001", Decimal("0"), "GRAM", 3), ("VAR-000001", Decimal("2"), "SET", 7)])
    assert snapshot.eligible.value == 2
    with pytest.raises(ProductionPlanningError):          # due righe vive: ambiguo
        _stock([("VAR-000001", Decimal("1"), "GRAM", 3), ("VAR-000001", Decimal("2"), "SET", 7)])
    with pytest.raises(ProductionPlanningError):          # tutte a zero ma nessuna riga SET: ambiguo
        _stock([("VAR-000001", Decimal("0"), "GRAM", 3), ("VAR-000001", Decimal("0"), "UNIT", 7)])
