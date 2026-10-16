"""Rotte del diario per gli incassi (16/10/2026): nessun database, nessun modello. Si verifica che la pagina
ottenga la proposta SENZA scrivere, che la scrittura avvenga solo con /api/conferma e che gli errori arrivino
leggibili."""
from fastapi.testclient import TestClient

from src.tpo_core.diario_web import app as app_module, incassi, interpreter

AUTH = ("matteo", "segreta")


def _client(monkeypatch):
    monkeypatch.setenv("DIARIO_PASSWORD", "segreta")
    monkeypatch.setattr(app_module, "_settings", lambda: object())
    return TestClient(app_module.app)


def _proposta(**extra):
    base = dict(consegne=[{"codice": "CON-000014", "data": "2026-10-13", "voci": ["Afila 1 SET"]}],
                cliente_nome="Abaluus", metodo="CONTANTI", data_pagamento="2026-10-15", importo=None)
    base.update(extra)
    return incassi.PropostaPagamento(**base)


def test_all_incasso_routes_require_the_password(monkeypatch):
    client = _client(monkeypatch)
    assert client.get("/api/da-incassare").status_code == 401
    assert client.post("/api/pagamento/prepara", json={}).status_code == 401
    assert client.post("/api/conferma", json={"proposta": {"tipo": "pagamento_consegna"}}).status_code == 401


def test_da_incassare_lists_clients_and_methods(monkeypatch):
    client = _client(monkeypatch)
    elenco = [incassi.ClienteDaIncassare("CLI-000014", "Abaluus", [
        incassi.ConsegnaDaIncassare("CON-000014", "2026-10-13", 2, ["Afila 1 SET"])])]
    monkeypatch.setattr(incassi, "da_incassare", lambda settings, oggi=None: elenco)
    dati = client.get("/api/da-incassare", auth=AUTH).json()
    assert dati["metodi"] == ["BONIFICO", "CONTANTI", "CARTA", "BIZUM", "ALTRO"]
    assert dati["clienti"][0]["cliente"] == "Abaluus"
    assert dati["clienti"][0]["consegne"] == [
        {"codice": "CON-000014", "data": "2026-10-13", "giorni": 2, "voci": ["Afila 1 SET"]}]


def test_prepare_proposes_without_writing_and_reports_refusals(monkeypatch):
    client = _client(monkeypatch)
    visti = []

    def finto_prepara(settings, codici, metodo, data=None, importo=None, oggi=None):
        visti.append((codici, metodo))
        if metodo is None:
            raise incassi.PagamentoNonPossibile("Manca il metodo di pagamento.")
        return _proposta()

    def vietato(*args, **kwargs):
        raise AssertionError("la proposta non deve scrivere")

    monkeypatch.setattr(incassi, "prepara_pagamento", finto_prepara)
    monkeypatch.setattr(incassi, "esegui_pagamento", vietato)
    ok = client.post("/api/pagamento/prepara", auth=AUTH, json={"consegne": ["CON-000014"], "metodo": "CONTANTI"}).json()
    assert ok["errori"] == [] and ok["proposte"][0]["tipo"] == "pagamento_consegna"
    assert ok["proposte"][0]["cliente_nome"] == "Abaluus" and ok["proposte"][0]["metodo"] == "CONTANTI"
    no = client.post("/api/pagamento/prepara", auth=AUTH, json={"consegne": ["CON-000014"]}).json()
    assert no["proposte"] == [] and no["errori"] == ["Manca il metodo di pagamento."]


def test_confirm_writes_only_what_the_card_shows(monkeypatch):
    client = _client(monkeypatch)
    scritto = []
    monkeypatch.setattr(incassi, "esegui_pagamento", lambda settings, p, actor: scritto.append((p, actor)) or "FATTO")
    risposta = client.post("/api/conferma", auth=AUTH, json={"proposta": {
        "tipo": "pagamento_consegna", "cliente_nome": "Abaluus", "metodo": "BIZUM", "data_pagamento": "2026-10-15",
        "importo": None, "consegne": [{"codice": "CON-000014", "data": "2026-10-13", "voci": ["Afila 1 SET"]}]}})
    assert risposta.json() == {"ok": True, "messaggio": "FATTO"}
    proposta, attore = scritto[0]
    assert [c["codice"] for c in proposta.consegne] == ["CON-000014"] and proposta.metodo == "BIZUM"
    assert attore == app_module.ACTOR


def test_confirm_failure_is_shown_not_hidden(monkeypatch):
    client = _client(monkeypatch)

    def fallisce(settings, p, actor):
        raise incassi.PagamentoFallito("CON-000014: no. Nulla e' stato registrato.")

    monkeypatch.setattr(incassi, "esegui_pagamento", fallisce)
    risposta = client.post("/api/conferma", auth=AUTH, json={"proposta": {
        "tipo": "pagamento_consegna", "cliente_nome": "A", "metodo": "CONTANTI", "data_pagamento": "2026-10-15",
        "consegne": [{"codice": "CON-000014"}]}})
    assert risposta.status_code == 409 and not risposta.json()["ok"]
    assert "Nulla e' stato registrato" in risposta.json()["messaggio"]
    incompleta = client.post("/api/conferma", auth=AUTH, json={"proposta": {"tipo": "pagamento_consegna"}})
    assert incompleta.status_code == 400


def _richiesta(**kw):
    base = dict(azione="pagamento_consegna", varieta_public_id=None, varieta_nome=None, semina_public_id=None,
                num_set=None, origin=None, physical_started_at=None, target_state=None, chiarimento=None,
                cliente_public_id="CLI-000014", consegne=None, metodo_pagamento=None, data_pagamento=None,
                importo=None)
    base.update(kw)
    return interpreter.RichiestaInterpretata(**base)


def test_free_text_without_codes_proposes_all_the_clients_open_deliveries(monkeypatch):
    client = _client(monkeypatch)
    elenco = [incassi.ClienteDaIncassare("CLI-000014", "Abaluus", [
        incassi.ConsegnaDaIncassare("CON-000014", "2026-10-13", 2, []),
        incassi.ConsegnaDaIncassare("CON-000021", "2026-10-14", 1, [])])]
    visti = []

    def finto_prepara(settings, codici, metodo, data=None, importo=None, oggi=None):
        visti.append((list(codici), metodo))
        if metodo is None:
            raise incassi.PagamentoNonPossibile("Manca il metodo di pagamento.")
        return _proposta()

    monkeypatch.setattr(incassi, "da_incassare", lambda settings, oggi=None: elenco)
    monkeypatch.setattr(incassi, "prepara_pagamento", finto_prepara)
    monkeypatch.setattr(interpreter, "interpreta", lambda testo, settings: [_richiesta(metodo_pagamento="CONTANTI")])
    dati = client.post("/api/interpreta", auth=AUTH, json={"testo": "Abaluus ha pagato in contanti"}).json()
    assert visti == [(["CON-000014", "CON-000021"], "CONTANTI")]
    assert dati["proposte"][0]["tipo"] == "pagamento_consegna" and dati["errori"] == []
    # metodo non detto: errore leggibile col nome del cliente, nessuna proposta
    monkeypatch.setattr(interpreter, "interpreta", lambda testo, settings: [_richiesta()])
    dati = client.post("/api/interpreta", auth=AUTH, json={"testo": "Abaluus ha pagato"}).json()
    assert dati["proposte"] == [] and dati["errori"] == ["Abaluus: Manca il metodo di pagamento."]
    # codici espliciti: solo quelli
    visti.clear()
    monkeypatch.setattr(interpreter, "interpreta",
                        lambda testo, settings: [_richiesta(consegne=("CON-000021",), metodo_pagamento="CARTA")])
    client.post("/api/interpreta", auth=AUTH, json={"testo": "Abaluus ha pagato CON-000021 con carta"})
    assert visti == [(["CON-000021"], "CARTA")]


def test_page_serves_the_incassi_section(monkeypatch):
    client = _client(monkeypatch)
    html = client.get("/", auth=AUTH).text
    assert 'id="incassi"' in html and "/api/pagamento/prepara" in html and "Segna come pagate" in html


def test_interpreter_prompt_carries_the_open_clients_and_the_payment_action():
    elenco = [incassi.ClienteDaIncassare("CLI-000014", "Abaluus", [
        incassi.ConsegnaDaIncassare("CON-000014", "2026-10-13", 2, []),
        incassi.ConsegnaDaIncassare("CON-000021", "2026-10-14", 1, [])])]
    prompt = interpreter._prompt_sistema([], elenco)
    assert "CLI-000014: Abaluus -> CON-000014, CON-000021" in prompt and "NON indovinarlo" in prompt
    assert "nessuna: tutte le consegne" in interpreter._prompt_sistema([], [])
    azioni = interpreter._TOOL["input_schema"]["properties"]["richieste"]["items"]["properties"]["azione"]["enum"]
    assert "pagamento_consegna" in azioni


def test_sessioni_semina_route_and_section(monkeypatch):
    from datetime import date
    from decimal import Decimal
    from src.tpo_core.diario_web import sessioni_semina as ss
    client = _client(monkeypatch)
    assert client.get("/api/sessioni-semina").status_code == 401
    riga = ss.RigaSemina("RPS-1", "Afila", "Gringo", "ORD-000001", date(2026, 10, 28), "PIANIFICATA", Decimal(2), "SET",
                         Decimal(60), date(2026, 10, 18), date(2026, 10, 28))
    visti = []

    def finto_piano(settings, oggi=None, giorni=ss.GIORNI_DEFAULT, n_sessioni=2, anticipo_max=3):
        visti.append(n_sessioni)
        return ss.assegna([riga], date(2026, 10, 15), giorni, n_sessioni)

    monkeypatch.setattr(ss, "piano", finto_piano)
    dati = client.get("/api/sessioni-semina?sessioni=3", auth=AUTH).json()
    assert visti == [3] and dati["giorni"] == ["mercoledi", "domenica"]
    assert dati["sessioni"][0]["varieta"][0]["destinatari"][0]["cliente"] == "Gringo"
    assert client.get("/", auth=AUTH).text.count('id="semine"') == 1
