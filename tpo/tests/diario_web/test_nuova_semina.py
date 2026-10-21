"""Schermata Nuova semina del diario (21/10/2026): lista varieta', anteprima esatta, conferma con scarico materiali.
Nessun database: le letture e i due comandi governati si sostituiscono con finti, cosi' si controlla COSA verrebbe scritto."""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src.tpo_core.diario_web import actions, app as app_module, nuova_semina as ns
from src.tpo_core.diario_web.actions import PropostaAmbigua, SeminaOperazioneFallita, TZ_LOCALE

AUTH = ("matteo", "segreta")
ADESSO = datetime(2026, 10, 21, 13, 30, tzinfo=TZ_LOCALE)          # mercoledi' 21/10/2026, 13:30 (ora legale: +01:00)


def _lotto(pid, residuo, racc="RACCOMANDATA", anomalia=None, scadenza=None, rating=None, ricevuto=date(2026, 9, 1),
           fornitore="Golinucci Organic", version=3):
    return ns.Lotto(pid, version, fornitore, "Ref", Decimal(residuo), scadenza, anomalia, racc,
                    Decimal(rating) if rating is not None else None, ricevuto)


def _var(pid, nome, g="14", lotti=(), protocolli=None, codice="XXX"):
    prot = ((f"PV-{pid[-3:]}", Decimal(g)),) if protocolli is None else protocolli
    return ns.VarietaOpzione(pid, nome, codice, prot, tuple(lotti))


CIL = _var("VAR-000003", "Cilantro", "14", [_lotto("LSE-000013", "116")], codice="CIL")
ACE = _var("VAR-000009", "Acetosella", "8", [_lotto("LSE-000009", "240")], codice="ACE")
SENZA_PROTOCOLLO = _var("VAR-000020", "Menta", lotti=[_lotto("LSE-000020", "50")], protocolli=())
LOTTO_CON_NOTA = _var("VAR-000021", "Senape", "10", [_lotto("LSE-000021", "500", anomalia="umido")])
LOTTO_SCADUTO = _var("VAR-000022", "Lenticchia", "30", [_lotto("LSE-000022", "500", scadenza=date(2026, 10, 1))])
SENZA_LOTTI = _var("VAR-000023", "Girasole", "28", [])
DUE_PROTOCOLLI = _var("VAR-000024", "Rucola", lotti=[_lotto("LSE-000024", "500")],
                      protocolli=(("PV-1", Decimal(5)), ("PV-2", Decimal(6))))


@pytest.fixture
def finti(monkeypatch):
    """Sostituisce le tre letture e i due comandi governati; registra cosa viene chiamato."""
    stato = {"opzioni": [CIL, ACE], "stock": {"vaschette": Decimal(2624), "substrato": Decimal(2624)},
             "semine": [], "comandi": [], "materiali": [], "materiali_errore": None}
    monkeypatch.setattr(ns, "leggi_opzioni", lambda settings: stato["opzioni"])
    monkeypatch.setattr(ns, "leggi_stock", lambda settings: stato["stock"])
    monkeypatch.setattr(ns, "semine_del_giorno", lambda settings, v, g: stato["semine"])

    def commissiona(args):
        stato["comandi"].append(args)
        return ("STATUS: INSERTED\nENTITY: SEMINA\nPUBLIC_ID: SEM-000053\nTRACEABILITY_CODE: ACE-2110-A\n"
                "STATE: AVVIATA\nSEED_LOT: LSE-000009")

    def consuma(semina, n, actor, marca):
        if stato["materiali_errore"]:
            raise SeminaOperazioneFallita(stato["materiali_errore"])
        stato["materiali"].append((semina, n, actor))

    monkeypatch.setattr(ns, "_esegui", commissiona)
    monkeypatch.setattr(ns, "_consuma_materiali", consuma)
    return stato


def _prepara(var="VAR-000009", n=1, giorno=date(2026, 10, 21), ora=time(12, 0), lotto=None, adesso=ADESSO):
    return ns.prepara(object(), var, n, giorno, ora, lotto, adesso)


# ------------------------------------------------------------------ lista

def test_lista_mette_prima_le_varieta_seminabili_e_dice_perche_le_altre_no() -> None:
    d = ns.a_dizionario([SENZA_PROTOCOLLO, CIL, LOTTO_CON_NOTA, LOTTO_SCADUTO, SENZA_LOTTI, DUE_PROTOCOLLI, ACE],
                        date(2026, 10, 21))
    assert [v["nome"] for v in d["varieta"]][:2] == ["Cilantro", "Acetosella"]
    motivi = {v["nome"]: v["motivo"] for v in d["varieta"] if not v["pronta"]}
    assert "protocollo" in motivi["Menta"]
    assert "anomalia" in motivi["Senape"] and "LSE-000021" in motivi["Senape"]
    assert "scaduto il 01/10/2026" in motivi["Lenticchia"]
    assert "nessun lotto" in motivi["Girasole"]
    assert "2 protocolli" in motivi["Rucola"]
    cil = d["varieta"][0]
    assert cil["g_per_set"] == "14" and cil["lotti"][0]["max_set"] == 8 and cil["protocollo"] == "PV-003"
    assert d["pezzi_per_set"] == 4 and d["set_max"] == ns.SET_MAX


def test_il_lotto_senza_seme_a_sufficienza_non_e_utilizzabile_ma_si_vede() -> None:
    poco = _var("VAR-000030", "Borragine", "8", [_lotto("LSE-000030", "5")])
    d = ns.a_dizionario([poco], date(2026, 10, 21))["varieta"][0]
    assert not d["pronta"] and "residuo 5 g, ne servono 8 g" in d["motivo"]


def test_ordine_dei_lotti_come_gli_script() -> None:
    v = ns.componi_opzioni(
        [("VAR-1", "Mizuna", "MIZ")], [("VAR-1", "PV-1", "10")],
        [("VAR-1", "LSE-B", 1, "F", "R", "100", None, None, "UTILIZZABILE", 5, date(2026, 10, 1)),
         ("VAR-1", "LSE-A", 1, "F", "R", "100", None, None, "RACCOMANDATA", 1, date(2026, 9, 1)),
         ("VAR-1", "LSE-C", 1, "F", "R", "100", None, None, "RACCOMANDATA", 1, date(2026, 9, 20))])[0]
    # prima i RACCOMANDATA, a parita' di rating il ricevuto per ultimo, poi gli UTILIZZABILE
    assert [l.public_id for l in v.lotti] == ["LSE-C", "LSE-A", "LSE-B"]
    assert ns.lotto_predefinito(v, date(2026, 10, 21), 1).public_id == "LSE-C"


# ------------------------------------------------------------------ anteprima

def test_anteprima_acetosella_come_lo_script(finti) -> None:
    p = _prepara()
    assert (p.varieta_nome, p.num_set, p.grammi, p.g_per_set) == ("Acetosella", "1", "8", "8")
    assert (p.lotto_seme_public_id, p.protocollo_versione_public_id, p.residuo_dopo) == ("LSE-000009", "PV-009", "232")
    assert (p.vaschette, p.substrati) == ("4", "4")
    assert p.physical_started_at == "2026-10-21T12:00:00+01:00" and p.tipo == "nuova_semina"
    assert ns.a_dizionario_proposta(p)["tipo"] == "nuova_semina"


def test_anteprima_cilantro_due_set(finti) -> None:
    p = _prepara("VAR-000003", 2)
    assert (p.grammi, p.residuo_dopo, p.vaschette) == ("28", "88", "8")


def test_l_ora_legale_finita_cambia_l_offset_senza_toccare_il_codice(finti) -> None:
    dopo = datetime(2026, 10, 26, 10, 0, tzinfo=TZ_LOCALE)      # dopo il 25/10 le Canarie tornano a +00:00
    p = _prepara(giorno=date(2026, 10, 26), ora=time(9, 0), adesso=dopo)
    assert p.physical_started_at == "2026-10-26T09:00:00+00:00"


def test_ora_non_indicata_oggi_vale_adesso_e_un_giorno_passato_le_12(finti) -> None:
    oggi = _prepara(ora=None)
    assert oggi.physical_started_at == "2026-10-21T13:30:00+01:00" and "vale adesso (13:30)" in " ".join(oggi.note)
    ieri = _prepara(giorno=date(2026, 10, 20), ora=None)
    assert ieri.physical_started_at == "2026-10-20T12:00:00+01:00" and "12:00" in " ".join(ieri.note)


def test_si_puo_scegliere_il_lotto(finti) -> None:
    finti["opzioni"] = [_var("VAR-000009", "Acetosella", "8", [_lotto("LSE-000009", "240"), _lotto("LSE-000099", "100", racc="UTILIZZABILE")])]
    assert _prepara().lotto_seme_public_id == "LSE-000009"
    assert _prepara(lotto="LSE-000099").lotto_seme_public_id == "LSE-000099"


@pytest.mark.parametrize("kwargs, frase", [
    ({"n": "1.5"}, "SET interi"),
    ({"n": "due"}, "non e' un numero"),
    ({"n": 0}, "almeno 1"),
    ({"n": 51}, "troppo"),
    ({"n": 31}, "residuo 240 g, ne servono 248 g"),            # 31 x 8 g > 240 g
    ({"giorno": date(2026, 10, 22)}, "futuro"),
    ({"ora": time(18, 0)}, "non sono ancora arrivate"),
    ({"giorno": date(2026, 9, 1)}, "troppo indietro"),
    ({"lotto": "LSE-000013"}, "non e' un lotto collegato"),
])
def test_rifiuta_senza_scrivere(finti, kwargs, frase) -> None:
    with pytest.raises(PropostaAmbigua) as exc:
        _prepara(**kwargs)
    assert frase in str(exc.value)
    assert finti["comandi"] == [] and finti["materiali"] == []


@pytest.mark.parametrize("var, frase", [
    (SENZA_PROTOCOLLO, "protocollo"), (SENZA_LOTTI, "nessun lotto"), (DUE_PROTOCOLLI, "2 protocolli"),
    (LOTTO_CON_NOTA, "anomalia"), (LOTTO_SCADUTO, "scaduto")])
def test_varieta_non_seminabili_dicono_il_motivo(finti, var, frase) -> None:
    finti["opzioni"] = [var]
    with pytest.raises(PropostaAmbigua) as exc:
        _prepara(var.public_id)
    assert frase in str(exc.value)


def test_avvisa_se_c_e_gia_una_semina_lo_stesso_giorno_o_alla_stessa_ora(finti) -> None:
    avvio = datetime(2026, 10, 21, 9, 0, tzinfo=TZ_LOCALE)
    finti["semine"] = [ns.SeminaEsistente("SEM-000050", "ACE-2110-X", avvio, Decimal(1), "SET")]
    assert any("seconda semina" in n and "ACE-2110-X" in n for n in _prepara().note)
    finti["semine"] = [ns.SeminaEsistente("SEM-000050", "ACE-2110-X", datetime(2026, 10, 21, 12, 0, tzinfo=TZ_LOCALE), Decimal(1), "SET")]
    assert any("NON si duplica" in n for n in _prepara().note)


def test_avvisa_se_vaschette_o_substrati_non_bastano(finti) -> None:
    finti["stock"] = {"vaschette": Decimal(2), "substrato": Decimal(2624)}
    note = " ".join(_prepara().note)
    assert "solo 2 vaschette" in note and "substrati" not in note


# ------------------------------------------------------------------ conferma

def test_conferma_registra_la_semina_poi_scala_i_materiali(finti) -> None:
    out = ns.esegui(object(), _prepara(), "giulia@towerpower", ADESSO)
    (a,) = finti["comandi"]
    assert (a.semina_command, a.seed_lot, a.expected_seed_lot_version, a.protocol_version) == ("commission", "LSE-000009", 3, "PV-009")
    assert (a.actual_seed_grams, a.origin, a.physical_started_at) == ("8", "RIPRISTINO_STOCK", "2026-10-21T12:00:00+01:00")
    assert a.confirm is True and a.planning_line is None and a.actor == "giulia@towerpower"
    assert "21/10/2026 ore 12:00 (1 SET, 8 g)" in a.reason and "cliente/ordine da assegnare in seguito" in a.reason
    assert finti["materiali"] == [("SEM-000053", 1, "giulia@towerpower")]
    assert "ACE-2110-A (SEM-000053)" in out and "4 vaschette + 4 substrati" in out and "residuo 232 g" in out


def test_la_chiave_di_idempotenza_dipende_da_istante_set_e_lotto(finti) -> None:
    ns.esegui(object(), _prepara(), "x", ADESSO)
    ns.esegui(object(), _prepara(ora=time(9, 0)), "x", ADESSO)
    ns.esegui(object(), _prepara(n=2), "x", ADESSO)
    chiavi = [a.idempotency_key for a in finti["comandi"]]
    assert len(set(chiavi)) == 3 and all(k.startswith("diario-nuova-semina-var-000009-") for k in chiavi)


def test_conferma_ripetuta_non_duplica_la_semina_ma_completa_i_materiali(finti) -> None:
    p = _prepara()
    finti["semine"] = [ns.SeminaEsistente("SEM-000053", "ACE-2110-A", datetime(2026, 10, 21, 12, 0, tzinfo=TZ_LOCALE), Decimal(1), "SET")]
    out = ns.esegui(object(), p, "x", ADESSO)
    assert finti["comandi"] == [] and finti["materiali"] == [("SEM-000053", 1, "x")]
    assert out.startswith("Semina gia' registrata: ACE-2110-A (SEM-000053)")


def test_se_i_materiali_falliscono_la_semina_resta_e_il_messaggio_lo_dice(finti) -> None:
    finti["materiali_errore"] = "CONSUMO_MATERIALI_FAILED: stock insufficiente"
    with pytest.raises(SeminaOperazioneFallita) as exc:
        ns.esegui(object(), _prepara(), "x", ADESSO)
    testo = str(exc.value)
    assert "ACE-2110-A (SEM-000053)" in testo and "NON sono stati scalati" in testo and "stock insufficiente" in testo
    assert "confermare di nuovo" in testo and len(finti["comandi"]) == 1


def test_dopo_l_anteprima_tutto_viene_riletto_e_se_e_cambiato_non_si_scrive(finti) -> None:
    p = _prepara()
    finti["opzioni"] = [CIL, _var("VAR-000009", "Acetosella", "10", [_lotto("LSE-000009", "240")])]      # g/SET cambiato
    with pytest.raises(SeminaOperazioneFallita) as exc:
        ns.esegui(object(), p, "x", ADESSO)
    assert "protocollo e' cambiato" in str(exc.value) and "Nulla registrato" in str(exc.value)
    finti["opzioni"] = [CIL, _var("VAR-000009", "Acetosella", "8", [_lotto("LSE-000009", "240", anomalia="muffa")])]
    with pytest.raises(SeminaOperazioneFallita) as exc:
        ns.esegui(object(), p, "x", ADESSO)
    assert "anomalia" in str(exc.value)
    assert finti["comandi"] == [] and finti["materiali"] == []


def test_non_si_registra_nel_futuro_ne_con_istante_senza_fuso(finti) -> None:
    p = _prepara()
    with pytest.raises(SeminaOperazioneFallita):
        ns.esegui(object(), p, "x", datetime(2026, 10, 21, 11, 0, tzinfo=TZ_LOCALE))             # prima dell'ora dichiarata
    senza_fuso = ns.PropostaNuovaSemina(**{**{k: getattr(p, k) for k in (
        "varieta_public_id", "varieta_nome", "num_set", "grammi", "g_per_set", "lotto_seme_public_id", "lotto_fornitore",
        "protocollo_versione_public_id", "residuo_dopo", "vaschette", "substrati")}, "physical_started_at": "2026-10-21T12:00:00"})
    with pytest.raises(SeminaOperazioneFallita):
        ns.esegui(object(), senza_fuso, "x", ADESSO)
    assert finti["comandi"] == []


# ------------------------------------------------------------------ rotte e pagina

def _client(monkeypatch):
    monkeypatch.setenv("DIARIO_PASSWORD", "segreta")
    monkeypatch.setattr(app_module, "_settings", lambda: object())
    return TestClient(app_module.app)


def test_rotte_richiedono_la_password_e_funzionano(monkeypatch, finti) -> None:
    c = _client(monkeypatch)
    assert c.get("/api/nuova-semina/opzioni").status_code == 401
    assert c.post("/api/nuova-semina/prepara", json={}).status_code == 401
    d = c.get("/api/nuova-semina/opzioni", auth=AUTH).json()
    assert [v["nome"] for v in d["varieta"]] == ["Cilantro", "Acetosella"]
    r = c.post("/api/nuova-semina/prepara", auth=AUTH, json={
        "varieta": "VAR-000003", "set": "2", "giorno": date.today().isoformat(), "ora": "00:00"}).json()
    assert r["errori"] == [] and r["proposte"][0]["grammi"] == "28" and r["proposte"][0]["tipo"] == "nuova_semina"


def test_prepara_errori_leggibili(monkeypatch, finti) -> None:
    c = _client(monkeypatch)
    r = c.post("/api/nuova-semina/prepara", auth=AUTH, json={"varieta": "VAR-000003", "set": "1.5", "giorno": "2026-10-21"}).json()
    assert r["proposte"] == [] and "SET interi" in r["errori"][0]
    r = c.post("/api/nuova-semina/prepara", auth=AUTH, json={"varieta": "VAR-000003", "set": "1", "giorno": "ieri"}).json()
    assert r["proposte"] == [] and "non validi" in r["errori"][0]


def test_conferma_passa_dal_percorso_unico_e_un_errore_diventa_409(monkeypatch, finti) -> None:
    c = _client(monkeypatch)
    p = ns.a_dizionario_proposta(_prepara())
    monkeypatch.setattr(ns, "esegui", lambda settings, proposta, attore: f"ok {proposta.varieta_nome} {proposta.num_set}")
    r = c.post("/api/conferma", auth=AUTH, json={"proposta": p})
    assert r.status_code == 200 and r.json() == {"ok": True, "messaggio": "ok Acetosella 1"}

    def rifiuta(settings, proposta, attore):
        raise SeminaOperazioneFallita("lotto cambiato. Nulla registrato.")

    monkeypatch.setattr(ns, "esegui", rifiuta)
    r = c.post("/api/conferma", auth=AUTH, json={"proposta": p})
    assert r.status_code == 409 and r.json()["ok"] is False and "Nulla registrato" in r.json()["messaggio"]
    r = c.post("/api/conferma", auth=AUTH, json={"proposta": {"tipo": "nuova_semina", "varieta_nome": "x"}})
    assert r.status_code == 400


def test_la_pagina_semine_ha_il_pulsante_e_il_pannello(monkeypatch) -> None:
    html = _client(monkeypatch).get("/", auth=AUTH).text
    for pezzo in ('id="btnNuovaSemina"', 'id="pannelloNuova"', "/api/nuova-semina/opzioni", "/api/nuova-semina/prepara",
                  'p.tipo === "nuova_semina"'):
        assert pezzo in html


# ------------------------------------------------------------------ materiali (vero comando di consumo, servizio finto)

def test_consumo_materiali_usa_il_comando_governato_con_4_pezzi_per_set(monkeypatch) -> None:
    visti = []

    def finto(args, *, stdout, stderr):
        visti.append(args)
        return 0

    monkeypatch.setattr(ns, "run_consumo_materiali_command", finto)
    ns._consuma_materiali("SEM-000053", 2, "giulia@towerpower", "marca")
    (a,) = visti
    assert (a.materiali_command, a.semina, a.set_seminati, a.pezzi_per_set) == ("consumo-semina", "SEM-000053", 2, 4)
    assert a.articolo_vaschette is None and a.articolo_substrato is None and a.effective_at is None
    assert a.confirm is True and a.correlation_id == "DIARIO-CONSUMO-SEM-000053" and a.actor == "giulia@towerpower"


def test_consumo_materiali_rifiutato_diventa_un_errore_con_il_testo_del_comando(monkeypatch) -> None:
    def rifiuta(args, *, stdout, stderr):
        print("CONSUMO_MATERIALI_FAILED: STOCK_INSUFFICIENTE: vaschette", file=stderr)
        return 4

    monkeypatch.setattr(ns, "run_consumo_materiali_command", rifiuta)
    with pytest.raises(SeminaOperazioneFallita) as exc:
        ns._consuma_materiali("SEM-000053", 1, "x", "m")
    assert "STOCK_INSUFFICIENTE" in str(exc.value)
