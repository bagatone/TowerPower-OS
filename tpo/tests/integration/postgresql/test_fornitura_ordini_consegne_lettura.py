from datetime import datetime, timezone
from decimal import Decimal
import uuid

from alembic import command as alembic_command
import pytest
import sqlalchemy as sa

from src.tpo_core.application.assegnazione_fisica.models import (
    AssegnazioneFisicaAuthority, RegistraAssegnazioneFisica,
)
from src.tpo_core.application.fornitura_ordini_consegne_lettura.models import (
    RichiediElencoAssegnazioniFisiche, RichiediElencoConsegne, RichiediElencoOrdini,
    RichiediElencoProgrammiFornitura,
)
from src.tpo_core.domain.identifiers import (
    ActorId, ConsegnaId, OrdineId, RaccoltaId, RigaOrdineId,
)
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.assegnazione_fisica import (
    PostgreSQLAssegnazioneFisicaWriter,
)
from src.tpo_core.infrastructure.postgresql.fornitura_ordini_consegne_lettura import (
    PostgreSQLFornituraOrdiniConsegneLetturaReader,
)
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql,
)
from tests.integration.postgresql.test_assegnazione_fisica import (
    _consegna, _ordine_con_riga, _riga_consegna,
)
from tests.integration.postgresql.test_raccolta import harvest, harvest_environment, ready
from tests.integration.postgresql.test_semina_commissioning import environment

BASE = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)


def _assegnazione_command(*, raccolta, riga_ordine="RO-000101", consegna=None,
                           quantita="50.5", key="assegna-lettura"):
    return RegistraAssegnazioneFisica(
        raccolta_id=RaccoltaId(raccolta),
        riga_ordine_id=RigaOrdineId(riga_ordine),
        quantita_assegnata=Decimal(quantita),
        unita_misura="GRAM",
        effective_at=BASE,
        motivo="assegnazione a cliente",
        authority=AssegnazioneFisicaAuthority(
            ActorId("operatore"), "assegnazione fisica", f"corr-{key}", key,
        ),
        consegna_id=ConsegnaId(consegna) if consegna else None,
    )


def _seed_programma_fornitura(engine):
    with engine.begin() as connection:
        programma_pk, cliente_pk = connection.exec_driver_sql(
            "INSERT INTO tpo.programmi_fornitura(public_id,cliente_id,created_by) "
            "SELECT 'PF-000001', id, 'test' FROM tpo.clienti WHERE public_id='CLI-000001' "
            "RETURNING id, cliente_id"
        ).one()
        versione_pk = connection.exec_driver_sql(
            "INSERT INTO tpo.programmi_fornitura_versioni(programma_fornitura_id,cliente_id,"
            "numero_versione,stato,data_inizio,finestra_operativa_giorni,valida_dal,created_by) "
            "VALUES (%s,%s,1,'ATTIVO',DATE '2026-09-01',2,%s,'test') RETURNING id",
            (programma_pk, cliente_pk, BASE),
        ).scalar_one()
        riga_pk = connection.exec_driver_sql(
            "INSERT INTO tpo.righe_programma_fornitura(programma_versione_id,posizione,"
            "varieta_id,quantita,unita_misura,tipo_ricorrenza) "
            "SELECT %s,1,id,30,'GRAM','GIORNI_SETTIMANA' FROM tpo.varieta "
            "WHERE public_id='VAR-000001' RETURNING id",
            (versione_pk,),
        ).scalar_one()
        connection.exec_driver_sql(
            "INSERT INTO tpo.righe_programma_giorni(riga_programma_id,giorno_iso) "
            "VALUES (%s,2),(%s,5)",
            (riga_pk, riga_pk),
        )


@pytest.fixture
def fornitura_environment(harvest_environment):
    engine, raccolta_writer = harvest_environment
    ready(engine)
    raccolta = raccolta_writer.record(harvest())
    _seed_programma_fornitura(engine)
    ordine_pk = _ordine_con_riga(engine, stato="PARZIALMENTE_EVASO")
    consegna_pk = _consegna(engine, ordine_pk=ordine_pk)
    _riga_consegna(engine, consegna_pk=consegna_pk, ordine_pk=ordine_pk,
                    riga_public_id="RO-000101")
    assegnazione_writer = PostgreSQLAssegnazioneFisicaWriter(_Factory(engine))
    assegnazione_writer.registra(
        _assegnazione_command(raccolta=raccolta.raccolta_id.value, consegna="CON-000101")
    )
    return engine


def test_programmi_fornitura_reads_current_version_with_righe_e_giorni(fornitura_environment):
    reader = PostgreSQLFornituraOrdiniConsegneLetturaReader(_Factory(fornitura_environment))
    result = reader.programmi_fornitura(RichiediElencoProgrammiFornitura())
    assert len(result.programmi) == 1
    programma = result.programmi[0]
    assert programma.programma_id.value == "PF-000001"
    assert programma.cliente_id.value == "CLI-000001"
    assert programma.numero_versione == 1
    assert programma.stato == "ATTIVO"
    assert len(programma.righe) == 1
    riga = programma.righe[0]
    assert riga.varieta_id.value == "VAR-000001"
    assert riga.tipo_ricorrenza == "GIORNI_SETTIMANA"
    assert riga.giorni_settimana == (2, 5)


def test_programmi_fornitura_ignora_versioni_voided(fornitura_environment):
    # Regressione (trovata su dati reali di produzione, PF-000001/Abaluus):
    # la query selezionava solo `valida_al IS NULL`, senza `voided_at IS NULL`.
    # Una versione corretta con `onboarding correct-never-effective-supply-program`
    # resta con valida_al NULL ma voided_at valorizzato (vedi
    # infrastructure/postgresql/onboarding.py, _run_raccolta_correggi-style update):
    # senza il filtro compariva ancora come "versione corrente" insieme a quella vera.
    engine = fornitura_environment
    with engine.begin() as connection:
        programma_pk, cliente_pk = connection.exec_driver_sql(
            "SELECT id, cliente_id FROM tpo.programmi_fornitura WHERE public_id='PF-000001'"
        ).one()
        vecchia_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.programmi_fornitura_versioni "
            "WHERE programma_fornitura_id=%s AND numero_versione=1", (programma_pk,)
        ).scalar_one()
        # Prima si libera lo slot "corrente" (indice unico parziale su
        # valida_al IS NULL AND voided_at IS NULL), poi si inserisce la nuova
        # versione — stesso ordine che una correzione reale osserverebbe.
        connection.exec_driver_sql(
            "UPDATE tpo.programmi_fornitura_versioni SET voided_at=%s,voided_by='test',"
            "void_reason='correzione test',void_correlation_id='corr-void-test' "
            "WHERE id=%s",
            (BASE, vecchia_pk),
        )
        nuova_pk = connection.exec_driver_sql(
            "INSERT INTO tpo.programmi_fornitura_versioni(programma_fornitura_id,cliente_id,"
            "numero_versione,stato,data_inizio,finestra_operativa_giorni,valida_dal,created_by) "
            "VALUES (%s,%s,2,'ATTIVO',DATE '2026-09-01',2,%s,'test') RETURNING id",
            (programma_pk, cliente_pk, BASE),
        ).scalar_one()
        connection.exec_driver_sql(
            "UPDATE tpo.programmi_fornitura_versioni SET replacement_version_id=%s WHERE id=%s",
            (nuova_pk, vecchia_pk),
        )
    reader = PostgreSQLFornituraOrdiniConsegneLetturaReader(_Factory(engine))
    result = reader.programmi_fornitura(RichiediElencoProgrammiFornitura())
    assert len(result.programmi) == 1
    assert result.programmi[0].numero_versione == 2


def test_ordini_reads_row_with_righe(fornitura_environment):
    # NOTA: harvest_environment -> environment seeda gia' ORD-000001/RO-000001
    # (tests.infrastructure.postgresql.test_production_planning_commit_writer
    # ._seed_authorities), quindi l'elenco contiene sia quello che ORD-000101
    # creato da questo fixture: la query e' corretta (nessun filtro in V1),
    # e' l'ambiente condiviso ad avere gia' un ordine.
    reader = PostgreSQLFornituraOrdiniConsegneLetturaReader(_Factory(fornitura_environment))
    result = reader.ordini(RichiediElencoOrdini())
    by_id = {o.ordine_id.value: o for o in result.ordini}
    assert set(by_id) == {"ORD-000001", "ORD-000101"}
    ordine = by_id["ORD-000101"]
    assert ordine.cliente_id.value == "CLI-000001"
    assert ordine.stato == "PARZIALMENTE_EVASO"
    assert ordine.tipo_creazione == "MANUALE"
    assert len(ordine.righe) == 1
    assert ordine.righe[0].varieta_id.value == "VAR-000001"
    assert ordine.righe[0].quantita == Decimal("100")


def test_consegne_reads_row_with_righe_e_ordini_collegati(fornitura_environment):
    reader = PostgreSQLFornituraOrdiniConsegneLetturaReader(_Factory(fornitura_environment))
    result = reader.consegne(RichiediElencoConsegne())
    assert len(result.consegne) == 1
    consegna = result.consegne[0]
    assert consegna.consegna_id.value == "CON-000101"
    assert consegna.stato == "CONSEGNATA"
    assert consegna.ordini_collegati == (OrdineId("ORD-000101"),)
    assert len(consegna.righe) == 1
    assert consegna.righe[0].e_rettifica is False
    assert consegna.righe[0].quantita == Decimal("10")


def test_assegnazioni_fisiche_reads_row_linked_to_consegna(fornitura_environment):
    reader = PostgreSQLFornituraOrdiniConsegneLetturaReader(_Factory(fornitura_environment))
    result = reader.assegnazioni_fisiche(RichiediElencoAssegnazioniFisiche())
    assert len(result.assegnazioni) == 1
    assegnazione = result.assegnazioni[0]
    assert assegnazione.raccolta_id.value == "RAC-000001"
    assert assegnazione.ordine_id.value == "ORD-000101"
    assert assegnazione.riga_ordine_posizione == 1
    assert assegnazione.consegna_id == ConsegnaId("CON-000101")
    assert assegnazione.quantita_assegnata == Decimal("50.5")


def test_elenco_empty_when_no_rows(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_fornitura_lettura_empty_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    with engine.begin() as connection:
        alembic_command.upgrade(make_config(connection=connection), "head")
    reader = PostgreSQLFornituraOrdiniConsegneLetturaReader(_Factory(engine))
    assert reader.programmi_fornitura(RichiediElencoProgrammiFornitura()).programmi == ()
    assert reader.ordini(RichiediElencoOrdini()).ordini == ()
    assert reader.consegne(RichiediElencoConsegne()).consegne == ()
    assert reader.assegnazioni_fisiche(RichiediElencoAssegnazioniFisiche()).assegnazioni == ()
