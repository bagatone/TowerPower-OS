"""Errori provider-neutral della query FORNITURA/ORDINI/CONSEGNE V1."""


class FornituraOrdiniConsegneLetturaError(Exception):
    code = "FORNITURA_ORDINI_CONSEGNE_LETTURA_FAILED"


class InvalidFornituraOrdiniConsegneLetturaQueryError(FornituraOrdiniConsegneLetturaError):
    code = "FORNITURA_ORDINI_CONSEGNE_LETTURA_INPUT_INVALID"
