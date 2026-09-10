"""Verifica la mappatura delle eccezioni applicative esistenti in risposte
HTTP (Owner Decision D3): non introduce nuove regole, traduce solo i
codici `.code` già definiti da ciascun boundary."""
from __future__ import annotations

from fastapi.testclient import TestClient

from src.tpo_core.application.disponibilita_commerciale.service import DisponibilitaCommercialeService
from src.tpo_core.infrastructure.postgresql.errors import PostgreSQLConnectionError
from src.tpo_core.web import deps


def test_not_found_diventa_404_json(client: TestClient) -> None:
    response = client.get("/api/clienti/CLI-999999")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "CLIENTI_LETTURA_CLIENTE_NOT_FOUND"


def test_not_found_diventa_404_html(client: TestClient) -> None:
    response = client.get("/clienti/CLI-999999")
    assert response.status_code == 404
    assert "CLIENTI_LETTURA_CLIENTE_NOT_FOUND" in response.text


def test_identificativo_malformato_diventa_400(client: TestClient) -> None:
    # "CLI1" non rispetta il formato PermanentId (PREFISSO-almeno 6 cifre):
    # è un errore di dominio (InvalidIdentifierError), non un bug -- 400.
    response = client.get("/api/clienti/CLI1")
    assert response.status_code == 400
    assert response.json()["code"] == "InvalidIdentifierError"


def test_database_non_raggiungibile_diventa_503(client: TestClient) -> None:
    class _FailingReader:
        def disponibilita(self, query):
            raise PostgreSQLConnectionError("Impossibile aprire la connessione PostgreSQL.")

    client.app.dependency_overrides[deps.get_disponibilita_commerciale_service] = (
        lambda: DisponibilitaCommercialeService(_FailingReader())
    )
    response = client.get("/api/disponibilita-commerciale/VAR-000002")
    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"
