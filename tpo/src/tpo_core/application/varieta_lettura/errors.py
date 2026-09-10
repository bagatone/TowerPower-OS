"""Errori provider-neutral della query VARIETA/LISTINO_VARIETA (sola lettura) V1."""


class VarietaLetturaError(Exception):
    code = "VARIETA_LETTURA_FAILED"


class InvalidVarietaLetturaQueryError(VarietaLetturaError):
    code = "VARIETA_LETTURA_INPUT_INVALID"


class VarietaLetturaVarietaNotFoundError(VarietaLetturaError):
    code = "VARIETA_LETTURA_VARIETA_NOT_FOUND"
