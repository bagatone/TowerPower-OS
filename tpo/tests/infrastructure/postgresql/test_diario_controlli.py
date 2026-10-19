"""Promemoria e controlli del diario (19/10/2026) su PostgreSQL usa-e-getta: le query girano sullo schema vero,
in sola lettura, e il risultato ha la forma che la pagina si aspetta."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tests.infrastructure.postgresql.test_chiusura_guidata_script import _semina
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)
from tests.infrastructure.postgresql.test_inventario_script import _connect

from src.tpo_core.diario_web import controlli, db_context


def test_le_query_girano_sullo_schema_vero_in_sola_lettura(writer_postgresql_engine, monkeypatch):
    engine = writer_postgresql_engine
    _semina(engine, 976001, "TST-1910-A", raccolto="0.5", atteso="2", stato="GERMINAZIONE")
    _semina(engine, 976002, "TST-1910-B", raccolto="0.5", atteso="3", stato="CRESCITA")
    _semina(engine, 976003, "TST-1910-C", raccolto="2", atteso="4", stato="PRONTA_ALLA_RACCOLTA")
    with engine.begin() as c:     # protocollo di prova (4 giorni di germinazione, 7 di luce), agganciato alle semine
        c.exec_driver_sql("SET LOCAL session_replication_role = replica")
        c.exec_driver_sql(
            "INSERT INTO tpo.protocollo_versioni(public_id,protocollo_id,numero_versione,valida_dal,contenuto,motivazione,"
            "stato_approvazione,idratazione_ore,orario_semina_previsto,orario_raccolta_target,germinazione_giorni,"
            "crescita_luce_giorni,grammi_seme_per_set,resa_attesa,resa_unita_misura,granularita_produttiva,"
            "harvest_min_lead_giorni,harvest_max_lead_giorni,buffer_temporale_minuti,provenance,approvata_at,approvata_by,"
            "created_by) VALUES ('PV-976001',1,1,DATE '2026-01-01','t','t','APPROVATA',8,TIME '06:00',TIME '06:00',4,7,25,"
            "1,'SET',0.5,1,2,0,'test',CURRENT_TIMESTAMP,'test','test')")
        c.exec_driver_sql("UPDATE tpo.semine SET protocollo_versione_id=(SELECT id FROM tpo.protocollo_versioni "
                          "WHERE public_id='PV-976001') WHERE public_id LIKE 'SEM-9760%%'")
    aperte = []

    def connessione(settings):
        aperte.append(_connect(engine))
        return aperte[-1]

    monkeypatch.setattr(db_context, "_connect", connessione)
    # molto dopo l'avvio delle semine (2098): ferme se il protocollo ha i giorni, altrimenti ignorate: in ogni caso nessun errore
    dati = controlli.leggi(object(), adesso=datetime(2098, 2, 1, 10, tzinfo=timezone.utc))

    assert set(dati) == {"aggiornato", "oggi", "promemoria", "anomalie", "nota"}
    assert set(dati["promemoria"]) == {"oggi", "domani", "in_ritardo"}
    assert all(a["tipo"] in {"semina_ferma", "clienti_simili", "seme_poco"} for a in dati["anomalie"])
    assert aperte[0].read_only is True            # la connessione del diario non puo' scrivere
    ferme = {a["semina"] for a in dati["anomalie"] if a["tipo"] == "semina_ferma"}
    assert {"SEM-976001", "SEM-976002"} <= ferme    # a febbraio 2098 sono ferme da mesi: le vede
    # la PRONTA_ALLA_RACCOLTA non e' una semina da far cambiare stadio: mai nel promemoria ne' tra le ferme
    assert "SEM-976003" not in ferme
    # e il giorno giusto: 4 giorni dopo l'avvio la germinazione e' da passare a luce
    avvio = engine.connect().exec_driver_sql("SELECT data_avvio FROM tpo.semine WHERE public_id='SEM-976001'").scalar_one()
    giorno = (avvio + timedelta(days=4)).astimezone(controlli.TZ).replace(hour=8)
    dati = controlli.leggi(object(), adesso=giorno)
    assert [v["semina"] for v in dati["promemoria"]["oggi"] if v["azione"] == "luce"] == ["SEM-976001"]


def test_semina_per_codice_in_sola_lettura(writer_postgresql_engine, monkeypatch):
    engine = writer_postgresql_engine
    _semina(engine, 976011, "TST-1910-K", raccolto="0.5", atteso="2", stato="GERMINAZIONE")
    aperte = []

    def connessione(settings):
        aperte.append(_connect(engine))
        return aperte[-1]

    monkeypatch.setattr(db_context, "_connect", connessione)
    d = db_context.semina_per_public_id(object(), "SEM-976011")
    assert d.public_id == "SEM-976011" and d.stato == "GERMINAZIONE" and d.codice_tracciabilita == "TST-1910-K"
    assert d.data_avvio.tzinfo is not None and d.varieta_nome and d.varieta_public_id.startswith("VAR-")
    assert db_context.semina_per_public_id(object(), "SEM-999999") is None
    assert all(c.read_only is True for c in aperte)
