"""Errori provider-neutral della lettura BOLLA DI CONSEGNA V1."""


class BollaLetturaError(Exception):
    code = "BOLLA_LETTURA_FAILED"


class InvalidBollaLetturaQueryError(BollaLetturaError):
    code = "BOLLA_LETTURA_INPUT_INVALID"


class ConsegnaNonTrovataError(BollaLetturaError):
    code = "BOLLA_CONSEGNA_NON_TROVATA"


class ConsegnaNonConsegnataError(BollaLetturaError):
    """La BOLLA si emette solo per una CONSEGNA realmente CONSEGNATA."""

    code = "BOLLA_CONSEGNA_NON_CONSEGNATA"
