"""Errori provider-neutral della query SEMENTE/LOTTO_SEME (sola lettura) V1."""


class SementeLetturaError(Exception):
    code = "SEMENTE_LETTURA_FAILED"


class InvalidSementeLetturaQueryError(SementeLetturaError):
    code = "SEMENTE_LETTURA_INPUT_INVALID"


class SementeLetturaLottoNotFoundError(SementeLetturaError):
    code = "SEMENTE_LETTURA_LOTTO_NOT_FOUND"
