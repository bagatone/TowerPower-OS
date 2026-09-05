"""Errori provider-neutral della query DISPONIBILITA_COMMERCIALE V1."""


class DisponibilitaCommercialeError(Exception):
    code = "DISPONIBILITA_COMMERCIALE_FAILED"


class InvalidDisponibilitaCommercialeQueryError(DisponibilitaCommercialeError):
    code = "DISPONIBILITA_COMMERCIALE_INPUT_INVALID"


class DisponibilitaCommercialeVarietaNotFoundError(DisponibilitaCommercialeError):
    code = "DISPONIBILITA_COMMERCIALE_VARIETA_NOT_FOUND"
