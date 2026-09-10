"""Errori provider-neutral della query MAGAZZINO (STOCK/MOVIMENTO/ARTICOLO) V1."""


class MagazzinoLetturaError(Exception):
    code = "MAGAZZINO_LETTURA_FAILED"


class InvalidMagazzinoLetturaQueryError(MagazzinoLetturaError):
    code = "MAGAZZINO_LETTURA_INPUT_INVALID"
