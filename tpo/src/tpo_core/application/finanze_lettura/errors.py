"""Errori provider-neutral della query FINANZE (FATTURA/INCASSO/USCITA) V1."""


class FinanzeLetturaError(Exception):
    code = "FINANZE_LETTURA_FAILED"


class InvalidFinanzeLetturaQueryError(FinanzeLetturaError):
    code = "FINANZE_LETTURA_INPUT_INVALID"
