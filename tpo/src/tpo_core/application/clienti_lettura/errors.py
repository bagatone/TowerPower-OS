"""Errori provider-neutral della query CLIENTI (sola lettura) V1."""


class ClientiLetturaError(Exception):
    code = "CLIENTI_LETTURA_FAILED"


class InvalidClientiLetturaQueryError(ClientiLetturaError):
    code = "CLIENTI_LETTURA_INPUT_INVALID"


class ClientiLetturaClienteNotFoundError(ClientiLetturaError):
    code = "CLIENTI_LETTURA_CLIENTE_NOT_FOUND"
