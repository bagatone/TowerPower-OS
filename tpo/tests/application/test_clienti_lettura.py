from datetime import datetime, timezone

import pytest

from src.tpo_core.application.clienti_lettura.errors import InvalidClientiLetturaQueryError
from src.tpo_core.application.clienti_lettura.models import (
    Cliente, ElencoClienti, RichiediCliente, RichiediElencoClienti,
)
from src.tpo_core.application.clienti_lettura.service import ClientiLetturaService
from src.tpo_core.domain.identifiers import ClienteId

NOW = datetime(2099, 1, 1, tzinfo=timezone.utc)


def test_richiedi_cliente_requires_cliente_id_type():
    with pytest.raises(InvalidClientiLetturaQueryError):
        RichiediCliente(cliente_id="CLI-000001")


def test_cliente_rejects_blank_denominazione():
    with pytest.raises(InvalidClientiLetturaQueryError):
        Cliente(ClienteId("CLI-000001"), "  ", None, None, NOW, NOW)


def test_cliente_allows_null_billing_fields():
    result = Cliente(ClienteId("CLI-000001"), "Bahia Real", None, None, NOW, NOW)
    assert result.modalita_fatturazione is None
    assert result.termini_pagamento_giorni is None


def test_cliente_rejects_invalid_modalita_fatturazione():
    with pytest.raises(InvalidClientiLetturaQueryError):
        Cliente(ClienteId("CLI-000001"), "Bahia Real", "ALTRO", None, NOW, NOW)


def test_cliente_rejects_non_positive_termini_pagamento():
    with pytest.raises(InvalidClientiLetturaQueryError):
        Cliente(ClienteId("CLI-000001"), "Bahia Real", None, 0, NOW, NOW)


def test_elenco_clienti_rejects_non_cliente_items():
    with pytest.raises(InvalidClientiLetturaQueryError):
        ElencoClienti(("not-a-cliente",))


def test_service_cliente_is_thin_and_typed():
    class Reader:
        def cliente(self, query):
            assert query == RichiediCliente(ClienteId("CLI-000001"))
            return "ok"

        def elenco(self, query):
            raise AssertionError("not expected")

    service = ClientiLetturaService(Reader())
    assert service.cliente(RichiediCliente(ClienteId("CLI-000001"))) == "ok"
    with pytest.raises(InvalidClientiLetturaQueryError):
        service.cliente(object())


def test_service_elenco_is_thin_and_typed():
    class Reader:
        def cliente(self, query):
            raise AssertionError("not expected")

        def elenco(self, query):
            assert query == RichiediElencoClienti()
            return "ok"

    service = ClientiLetturaService(Reader())
    assert service.elenco(RichiediElencoClienti()) == "ok"
    with pytest.raises(InvalidClientiLetturaQueryError):
        service.elenco(object())
