from datetime import timedelta
from decimal import Decimal

import pytest

from src.tpo_core.application.semina_raccolta_lettura.errors import (
    SeminaRaccoltaLetturaSeminaNotFoundError,
)
from src.tpo_core.application.semina_raccolta_lettura.models import (
    RichiediElencoSemine, RichiediSemina,
)
from src.tpo_core.domain.identifiers import SeminaId
from src.tpo_core.infrastructure.postgresql.semina_raccolta_lettura import (
    PostgreSQLSeminaRaccoltaLetturaReader,
)
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql,
)
from tests.integration.postgresql.test_raccolta import (
    BASE, environment, harvest, harvest_environment, ready,
)


def _insert_second_semina(engine, *, public_id="SEM-000002", stato="AVVIATA",
                           data_avvio="2026-08-20 08:00:00+00", discriminator="B"):
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
                   %s,2,'GRAM',
                   %s::timestamptz,'ORDINE_CLIENTE',
                   'Afila','Microgreen','LOT-1','PV-000001','test',%s
            FROM tpo.varieta v
            JOIN tpo.cultivar c ON c.varieta_id=v.id
            JOIN tpo.cultivar_usi cu ON cu.cultivar_id=c.id
            CROSS JOIN tpo.lotti_seme l
            CROSS JOIN tpo.protocollo_versioni pv
            WHERE v.public_id='VAR-000001' AND l.public_id='LSE-000001'
              AND pv.public_id='PV-000001'
            """,
            (public_id, stato, data_avvio, f"AFI-2508-{discriminator}"),
        )


def test_semina_reads_row_with_no_raccolte(harvest_environment):
    engine, _writer = harvest_environment
    reader = PostgreSQLSeminaRaccoltaLetturaReader(_Factory(engine))
    result = reader.semina(RichiediSemina(SeminaId("SEM-000001")))
    assert result.semina_id == SeminaId("SEM-000001")
    assert result.varieta_id.value == "VAR-000001"
    assert result.varieta_denominazione == "Writer test variety"
    assert result.stato == "AVVIATA"
    assert result.quantita_seme == Decimal("1.25")
    assert result.unita_misura == "GRAM"
    assert result.causa_origine == "ORDINE_CLIENTE"
    assert result.esito_finale is None
    assert result.cultivar_snapshot == "Afila"
    assert result.lotto_seme_snapshot == "LSE-000001"
    assert result.raccolte == ()


def test_semina_reads_row_with_raccolte_ordered_by_data(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    first = writer.record(harvest("harvest-1", quantity="0.5", at=BASE + timedelta(minutes=5)))
    second = writer.record(harvest("harvest-2", quantity="1.25", at=BASE))
    reader = PostgreSQLSeminaRaccoltaLetturaReader(_Factory(engine))
    result = reader.semina(RichiediSemina(SeminaId("SEM-000001")))
    assert result.stato == "PRONTA_ALLA_RACCOLTA"
    assert [r.raccolta_id for r in result.raccolte] == [second.raccolta_id, first.raccolta_id]
    assert [r.quantita for r in result.raccolte] == [Decimal("1.25"), Decimal("0.5")]
    assert all(r.unita_misura == "SET" for r in result.raccolte)
    assert all(r.semina_id == SeminaId("SEM-000001") for r in result.raccolte)


def test_semina_raises_when_not_found(harvest_environment):
    engine, _ = harvest_environment
    reader = PostgreSQLSeminaRaccoltaLetturaReader(_Factory(engine))
    with pytest.raises(SeminaRaccoltaLetturaSeminaNotFoundError):
        reader.semina(RichiediSemina(SeminaId("SEM-999999")))


def test_elenco_orders_by_data_avvio_descending_and_groups_raccolte(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    writer.record(harvest())
    _insert_second_semina(engine, public_id="SEM-000002", data_avvio="2026-09-01 08:00:00+00")
    reader = PostgreSQLSeminaRaccoltaLetturaReader(_Factory(engine))
    result = reader.elenco(RichiediElencoSemine())
    ids = [s.semina_id.value for s in result.semine]
    assert ids == ["SEM-000002", "SEM-000001"]
    by_id = {s.semina_id.value: s for s in result.semine}
    assert len(by_id["SEM-000001"].raccolte) == 1
    assert by_id["SEM-000002"].raccolte == ()


def test_elenco_empty_when_no_semine(environment):
    engine, _ = environment
    reader = PostgreSQLSeminaRaccoltaLetturaReader(_Factory(engine))
    result = reader.elenco(RichiediElencoSemine())
    assert result.semine == ()
