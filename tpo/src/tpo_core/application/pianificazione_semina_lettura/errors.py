"""Errori provider-neutral della query "Da seminare" (sola lettura) V1."""


class PianificazioneSeminaLetturaError(Exception):
    code = "PIANIFICAZIONE_SEMINA_LETTURA_FAILED"


class InvalidPianificazioneSeminaLetturaQueryError(PianificazioneSeminaLetturaError):
    code = "PIANIFICAZIONE_SEMINA_LETTURA_INPUT_INVALID"
