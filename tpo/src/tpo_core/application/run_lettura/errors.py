"""Errori provider-neutral della query RUN/RUN_LOG (sola lettura) V1."""


class RunLetturaError(Exception):
    code = "RUN_LETTURA_FAILED"


class InvalidRunLetturaQueryError(RunLetturaError):
    code = "RUN_LETTURA_INPUT_INVALID"


class RunLetturaRunNotFoundError(RunLetturaError):
    code = "RUN_LETTURA_RUN_NOT_FOUND"
