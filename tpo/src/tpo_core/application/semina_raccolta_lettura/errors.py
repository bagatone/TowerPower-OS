"""Errori provider-neutral della query SEMINA/RACCOLTA (sola lettura) V1."""


class SeminaRaccoltaLetturaError(Exception):
    code = "SEMINA_RACCOLTA_LETTURA_FAILED"


class InvalidSeminaRaccoltaLetturaQueryError(SeminaRaccoltaLetturaError):
    code = "SEMINA_RACCOLTA_LETTURA_INPUT_INVALID"


class SeminaRaccoltaLetturaSeminaNotFoundError(SeminaRaccoltaLetturaError):
    code = "SEMINA_RACCOLTA_LETTURA_SEMINA_NOT_FOUND"
