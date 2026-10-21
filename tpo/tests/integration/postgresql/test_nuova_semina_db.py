"""Nuova semina del diario (21/10/2026) su PostgreSQL usa-e-getta con lo schema vero: le tre letture (varieta' +
protocolli + lotti, semine del giorno, giacenze) e la conferma end-to-end con il comando di commissioning vero."""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

import psycopg
import pytest

from src.tpo_core.application.semina_commissioning import SeminaCommissioningService
from src.tpo_core.cli import semina as cli_semina
from src.tpo_core.diario_web import db_context, nuova_semina as ns
from src.tpo_core.diario_web.actions import SeminaOperazioneFallita, TZ_LOCALE
from tests.integration.postgresql.test_semina_commissioning import environment  # noqa: F401
from tests.infrastructure.postgresql.test_production_planning_migrations import isolated_postgresql  # noqa: F401

ADESSO = datetime(2026, 10, 21, 13, 30, tzinfo=TZ_LOCALE)


def _conn(engine):
    u = engine.url
    return psycopg.connect(host=u.host, port=u.port, dbname=u.database, user=u.username, password=u.password)


@pytest.fixture
def db(environment, monkeypatch):  # noqa: F811
    engine, _writer = environment
    with engine.begin() as c:       # un lotto capiente (25 g/SET nel protocollo di prova): 500 g
        c.exec_driver_sql("UPDATE tpo.lotti_seme SET quantita_iniziale=500, quantita_residua=500 WHERE public_id='LSE-000001'")
    aperte = []

    def connessione(settings):
        aperte.append(_conn(engine))
        return aperte[-1]

    monkeypatch.setattr(db_context, "_connect", connessione)
    # il comando di commissioning e' quello vero (CLI -> service -> writer), ma sul database usa-e-getta:
    # le impostazioni di produzione (SSL obbligatorio) non servono qui
    monkeypatch.setattr(cli_semina.PostgreSQLSettings, "from_environment", classmethod(lambda cls: object()))
    monkeypatch.setattr(cli_semina, "build_semina_commissioning_service",
                        lambda settings: SeminaCommissioningService(_writer))
    monkeypatch.setattr(ns, "_consuma_materiali", lambda *a: None)       # i materiali hanno il loro test
    yield engine, aperte
    for c in aperte:
        c.close()


def test_le_letture_vedono_protocollo_e_lotti_e_non_scrivono(db) -> None:
    engine, aperte = db
    opzioni = ns.leggi_opzioni(object())
    v = next(x for x in opzioni if x.public_id == "VAR-000001")
    assert v.protocolli == (("PV-000001", Decimal(25)),)
    assert [l.public_id for l in v.lotti][0] == "LSE-000001"
    assert {l.public_id for l in v.lotti} == {"LSE-000001", "LSE-000002", "LSE-000003", "LSE-000005"}     # LSE-000004 e' di un altro seme
    per_id = {l.public_id: l for l in v.lotti}
    assert per_id["LSE-000003"].anomalia == "damaged" and per_id["LSE-000002"].scadenza == date(2026, 8, 24)
    assert ns.motivo_varieta(v, date(2026, 10, 21)) is None
    assert "anomalia" in ns.motivo_lotto(per_id["LSE-000003"], Decimal(25), date(2026, 10, 21))
    assert "scaduto" in ns.motivo_lotto(per_id["LSE-000002"], Decimal(25), date(2026, 10, 21))
    assert all(c.read_only for c in aperte)
    d = ns.a_dizionario(opzioni, date(2026, 10, 21))["varieta"][0]
    assert d["nome"] == "Writer test variety" and d["pronta"] and d["g_per_set"] == "25"
    assert d["lotti"][0]["max_set"] == 20


def test_giacenze_e_semine_del_giorno(db) -> None:
    engine, _ = db
    assert ns.leggi_stock(object()) == {"vaschette": None, "substrato": None}
    with engine.begin() as c:
        c.exec_driver_sql("INSERT INTO tpo.articoli(public_id,denominazione,unita_misura,created_by) VALUES "
                          "('ART-990001','Vaschette','UNIT','t'),('ART-990002','Substrato fibra di cocco','UNIT','t')")
        for art, q in (("ART-990001", 2624), ("ART-990002", 2600)):
            c.exec_driver_sql("INSERT INTO tpo.stock_articoli(articolo_id,disponibile,unita_misura,updated_at,version) "
                              "SELECT id,%s,'UNIT',CURRENT_TIMESTAMP,0 FROM tpo.articoli WHERE public_id=%s", (q, art))
    assert ns.leggi_stock(object()) == {"vaschette": Decimal(2624), "substrato": Decimal(2600)}
    assert ns.semine_del_giorno(object(), "VAR-000001", date(2026, 10, 21)) == []


def test_conferma_end_to_end_registra_una_sola_semina_anche_se_confermata_due_volte(db) -> None:
    engine, _ = db
    p = ns.prepara(object(), "VAR-000001", 2, date(2026, 10, 21), time(12, 0), adesso=ADESSO)
    assert (p.grammi, p.lotto_seme_public_id, p.residuo_dopo) == ("50", "LSE-000001", "450")
    out = ns.esegui(object(), p, "giulia@towerpower", ADESSO)
    assert out.startswith("Semina registrata:") and "SEM-" in out and "2 SET Writer test variety" in out
    with engine.connect() as c:
        righe = c.exec_driver_sql(
            "SELECT s.public_id, s.codice_tracciabilita, s.data_avvio, l.quantita_residua "
            "FROM tpo.semine s JOIN tpo.lotti_seme l ON l.id=s.lotto_seme_id").all()
    assert len(righe) == 1 and righe[0][3] == Decimal(450)
    assert righe[0][2].astimezone(TZ_LOCALE).strftime("%d/%m/%Y %H:%M") == "21/10/2026 12:00"
    # seconda conferma identica: la semina c'e' gia', non si duplica e il lotto non scende ancora
    out2 = ns.esegui(object(), p, "giulia@towerpower", ADESSO)
    assert out2.startswith("Semina gia' registrata:")
    with engine.connect() as c:
        assert c.exec_driver_sql("SELECT count(*) FROM tpo.semine").scalar_one() == 1
        assert c.exec_driver_sql("SELECT quantita_residua FROM tpo.lotti_seme WHERE public_id='LSE-000001'").scalar_one() == Decimal(450)
    # ora la semina compare tra quelle del giorno e l'anteprima avvisa
    assert ns.semine_del_giorno(object(), "VAR-000001", date(2026, 10, 21))[0].public_id == righe[0][0]
    assert any("NON si duplica" in n for n in ns.prepara(object(), "VAR-000001", 2, date(2026, 10, 21), time(12, 0), adesso=ADESSO).note)


def test_lotto_che_cambia_dopo_l_anteprima_non_scrive(db) -> None:
    engine, _ = db
    p = ns.prepara(object(), "VAR-000001", 1, date(2026, 10, 21), time(12, 0), adesso=ADESSO)
    with engine.begin() as c:
        c.exec_driver_sql("UPDATE tpo.lotti_seme SET anomalia='muffa' WHERE public_id='LSE-000001'")
    with pytest.raises(SeminaOperazioneFallita) as exc:
        ns.esegui(object(), p, "x", ADESSO)
    assert "anomalia" in str(exc.value) and "Nulla registrato" in str(exc.value)
    with engine.connect() as c:
        assert c.exec_driver_sql("SELECT count(*) FROM tpo.semine").scalar_one() == 0
