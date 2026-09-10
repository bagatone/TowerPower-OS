"""Verifica che ogni pagina/endpoint dei 9 boundary Fase 1 risponda 200,
sia in JSON (`/api/...`) sia in HTML (`/...`), con dati iniettati tramite
reader finti (vedi conftest.py). Non è un test contro PostgreSQL: verifica
il web adapter (routing, dependency injection, serializzazione), non le
query SQL reali (già coperte da tests/integration/postgresql)."""
from __future__ import annotations

import pytest

# (metodo HTTP implicito GET) percorso JSON, percorso HTML
_LIST_ROUTES = [
    ("/api/clienti", "/clienti"),
    ("/api/varieta", "/varieta"),
    ("/api/sementi", "/sementi"),
    ("/api/lotti-seme", "/lotti-seme"),
    ("/api/semine", "/semine"),
    ("/api/magazzino/articoli", "/magazzino/articoli"),
    ("/api/magazzino/stock", "/magazzino/stock"),
    ("/api/magazzino/movimenti", "/magazzino/movimenti"),
    ("/api/programmi-fornitura", "/programmi-fornitura"),
    ("/api/ordini", "/ordini"),
    ("/api/consegne", "/consegne"),
    ("/api/assegnazioni-fisiche", "/assegnazioni-fisiche"),
    ("/api/fatture", "/fatture"),
    ("/api/incassi", "/incassi"),
    ("/api/uscite", "/uscite"),
    ("/api/run", "/run"),
]

_DETAIL_ROUTES = [
    ("/api/clienti/CLI-000001", "/clienti/CLI-000001"),
    ("/api/varieta/VAR-000002", "/varieta/VAR-000002"),
    ("/api/disponibilita-commerciale/VAR-000002", "/disponibilita-commerciale/VAR-000002"),
    ("/api/lotti-seme/LSE-000019", "/lotti-seme/LSE-000019"),
    ("/api/semine/SEM-000001", "/semine/SEM-000001"),
    ("/api/run/RUN-000001/log", "/run/RUN-000001/log"),
]


def test_home_page(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Sala Operativa" in response.text


@pytest.mark.parametrize("json_path,html_path", _LIST_ROUTES)
def test_elenco_json_e_html(client, json_path: str, html_path: str) -> None:
    json_response = client.get(json_path)
    assert json_response.status_code == 200, json_response.text
    assert isinstance(json_response.json(), dict)

    html_response = client.get(html_path)
    assert html_response.status_code == 200, html_response.text
    assert "text/html" in html_response.headers["content-type"]


@pytest.mark.parametrize("json_path,html_path", _DETAIL_ROUTES)
def test_dettaglio_json_e_html(client, json_path: str, html_path: str) -> None:
    json_response = client.get(json_path)
    assert json_response.status_code == 200, json_response.text
    assert isinstance(json_response.json(), dict)

    html_response = client.get(html_path)
    assert html_response.status_code == 200, html_response.text


def test_varieta_dettaglio_include_disponibilita_commerciale(client) -> None:
    response = client.get("/api/varieta/VAR-000002")
    body = response.json()
    assert body["disponibilita_commerciale"] is not None
    assert body["disponibilita_commerciale"]["vendibile"] == "60"


def test_elenco_clienti_contiene_il_cliente_atteso(client) -> None:
    response = client.get("/api/clienti")
    assert response.json()["clienti"][0]["cliente_id"] == "CLI-000001"


def test_pagina_lista_linka_al_dettaglio(client) -> None:
    response = client.get("/clienti")
    assert 'href="/clienti/CLI-000001"' in response.text


def test_magazzino_stock_espone_entrambe_le_sezioni(client) -> None:
    response = client.get("/api/magazzino/stock")
    body = response.json()
    assert body["stock_varieta"][0]["varieta_id"] == "VAR-000002"
    assert body["stock_articoli"][0]["articolo_id"] == "ART-000001"

    html_response = client.get("/magazzino/stock")
    assert "Stock varietà" in html_response.text
    assert "Stock articoli" in html_response.text
