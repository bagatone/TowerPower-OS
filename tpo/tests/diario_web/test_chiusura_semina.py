"""Chiusura di una semina dal diario (20/10/2026): proposta, esecuzione sul comando governato, rotte. Nessun database."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from src.tpo_core.diario_web import actions, app as app_module, db_context

AUTH = ("matteo", "segreta")
TZ = ZoneInfo("Atlantic/Canary")
ADESSO = datetime(2026, 10, 20, 9, 14, 30, tzinfo=TZ)
AVVIO = datetime(2026, 9, 29, 9, 0, tzinfo=TZ)


def _dett(stato="LUCE", raccolte=0, ultimo=datetime(2026, 10, 3, 10, 0, tzinfo=TZ), pid="SEM-000011", nome="Afila"):
    return db_context.SeminaDettaglio(pid, stato, 4, "AFI-2909-A", AVVIO, "VAR-1", nome, ultimo, raccolte)


def _prep(monkeypatch, dett=None, **kw):
    monkeypatch.setattr(db_context, "semina_per_public_id", lambda s, pid: dett)
    args = dict(esito="raccolta completa", venduti="6", scartati="0", nota=None, giorno=None, ora=None, adesso=ADESSO)
    args.update(kw)
    return actions.prepara_chiusura(object(), "SEM-000011", args.pop("esito"), args.pop("venduti"),
                                    args.pop("scartati"), args.pop("nota"), args.pop("giorno"), args.pop("ora"),
                                    args.pop("adesso"))


def test_venduta_tutta_oggi_adesso(monkeypatch) -> None:
    p = _prep(monkeypatch, _dett())
    assert (p.esito, p.venduti, p.scartati) == ("raccolta completa", "6", "0")
    assert p.istante == "2026-10-20T09:14:00+01:00"
    assert "6 SET venduto (vendita non registrata)" in p.motivo and "scartato" not in p.motivo
    assert "Chiusura SEM-000011 (Afila 29/09/2026) dichiarata da Matteo il 20/10/2026" in p.motivo
    assert p.motivo.endswith("Nessuna RACCOLTA ne' movimento di magazzino registrato per questa semina.")


def test_venduta_in_parte_con_scarto_giorno_passato_e_nota(monkeypatch) -> None:
    p = _prep(monkeypatch, _dett(), esito="raccolta parziale con scarto", venduti="1,5", scartati="0.5",
              nota="collassata in luce", giorno=date(2026, 10, 18))
    assert (p.venduti, p.scartati) == ("1.5", "0.5") and p.istante == "2026-10-18T12:00:00+01:00"
    assert "1.5 SET venduto" in p.motivo and "0.5 SET scartato" in p.motivo and "; collassata in luce." in p.motivo
    assert p.note and "12:00" in p.note[0]


def test_nessuna_quantita_dichiarata(monkeypatch) -> None:
    p = _prep(monkeypatch, _dett(), esito="interruzione", venduti=None, scartati="")
    assert "nessuna quantita dichiarata" in p.motivo


@pytest.mark.parametrize("dett,kw,testo", [
    (_dett("CHIUSA"), {}, "gia' CHIUSA"),
    (_dett(raccolte=2), {}, "2 raccolte registrate"),
    (_dett(), {"esito": "venduta"}, "Esito non riconosciuto"),
    (_dett(), {"venduti": "abc"}, "non e' un numero"),
    (_dett(), {"scartati": "-1"}, "negativo"),
    (_dett(), {"giorno": date(2026, 10, 21)}, "futuro"),
    (_dett(), {"giorno": date(2026, 10, 2)}, "troppo presto"),
])
def test_proposte_rifiutate(monkeypatch, dett, kw, testo) -> None:
    with pytest.raises(actions.PropostaAmbigua, match=testo):
        _prep(monkeypatch, dett, **kw)


def test_semina_inesistente(monkeypatch) -> None:
    with pytest.raises(actions.SeminaNonTrovata):
        _prep(monkeypatch, None)


def _proposta(**kw):
    base = dict(semina_public_id="SEM-000011", varieta_nome="Afila", stato_attuale="LUCE", esito="raccolta completa",
                venduti="6", scartati="0", nota="", istante=(datetime.now(TZ) - timedelta(hours=1)).isoformat(),
                motivo="TESTO FALSO DALLA PAGINA")
    base.update(kw)
    return actions.PropostaChiusura(**base)


def test_esecuzione_usa_il_comando_governato_e_ricompone_il_motivo(monkeypatch) -> None:
    visti = []
    monkeypatch.setattr(actions, "run_semina_command", lambda args, *, stdout, stderr: (visti.append(args), stdout.write("STATUS: INSERTED") and 0)[1] or 0)
    monkeypatch.setattr(db_context, "semina_per_public_id", lambda s, pid: _dett())
    actions.esegui_chiusura(object(), _proposta(), "matteo")
    a = visti[0]
    assert (a.target_state, a.final_outcome, a.expected_semina_version, a.semina) == ("CHIUSA", "raccolta completa", 4, "SEM-000011")
    assert "TESTO FALSO" not in a.reason and "6 SET venduto" in a.reason          # il motivo non viene dalla pagina
    assert '"final_outcome":"OWNER_AUTHORIZED"' in a.provenance and a.confirm is True
    assert a.idempotency_key == "diario-chiusura-sem-000011"


@pytest.mark.parametrize("kw,dett", [
    ({"istante": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}, _dett()),
    ({"istante": "2026-10-18T12:00:00"}, _dett()),
    ({"esito": "boh"}, _dett()),
    ({"venduti": "x"}, _dett()),
    ({}, _dett("CHIUSA")),
    ({}, _dett(raccolte=1)),
])
def test_esecuzione_rifiutata_senza_scrivere(monkeypatch, kw, dett) -> None:
    visti = []
    monkeypatch.setattr(actions, "run_semina_command", lambda args, *, stdout, stderr: visti.append(args) or 0)
    monkeypatch.setattr(db_context, "semina_per_public_id", lambda s, pid: dett)
    with pytest.raises((actions.SeminaOperazioneFallita, actions.SeminaNonTrovata)):
        actions.esegui_chiusura(object(), _proposta(**kw), "matteo")
    assert visti == []


def _client(monkeypatch):
    monkeypatch.setenv("DIARIO_PASSWORD", "segreta")
    monkeypatch.setattr(app_module, "_settings", lambda: object())
    return TestClient(app_module.app)


def test_rotte(monkeypatch) -> None:
    c = _client(monkeypatch)
    assert c.post("/api/chiusura/prepara", json={}).status_code == 401
    monkeypatch.setattr(db_context, "semina_per_public_id", lambda s, pid: _dett())
    r = c.post("/api/chiusura/prepara", auth=AUTH, json={"semina": "SEM-000011", "esito": "raccolta completa",
                                                           "venduti": "6", "scartati": "0", "giorno": "2026-10-18", "ora": "10:00"})
    p = r.json()["proposte"][0]
    assert r.json()["errori"] == [] and p["tipo"] == "semina_chiusura" and p["istante"] == "2026-10-18T10:00:00+01:00"
    r = c.post("/api/chiusura/prepara", auth=AUTH, json={"semina": "SEM-000011", "esito": "x"})
    assert "Esito non riconosciuto" in r.json()["errori"][0]
    r = c.post("/api/chiusura/prepara", auth=AUTH, json={"semina": "SEM-000011", "esito": "interruzione", "giorno": "ieri"})
    assert r.json()["errori"] == ["Giorno o ora non validi."]
    eseguiti = []
    monkeypatch.setattr(actions, "esegui_chiusura", lambda s, prop, actor: eseguiti.append(prop) or "FATTO")
    assert c.post("/api/conferma", auth=AUTH, json={"proposta": p}).json() == {"ok": True, "messaggio": "FATTO"}
    assert eseguiti[0].esito == "raccolta completa" and eseguiti[0].venduti == "6"
    assert c.post("/api/conferma", auth=AUTH, json={"proposta": {"tipo": "semina_chiusura"}}).status_code == 400


def test_la_pagina_ha_i_bottoni_chiudi(monkeypatch) -> None:
    html = _client(monkeypatch).get("/", auth=AUTH).text
    assert "/api/chiusura/prepara" in html and "data-chiudi=" in html and "data-chiudi-mag" in html and "data-avanza-mag" in html and html.count('id="registraMag"') == 1
