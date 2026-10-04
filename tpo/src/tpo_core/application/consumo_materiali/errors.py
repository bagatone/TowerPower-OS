"""Errori provider-neutral del boundary CONSUMO_MATERIALI_SEMINA V1."""


class ConsumoMaterialiError(Exception):
    code = "CONSUMO_MATERIALI_FAILED"


class InvalidConsumoMaterialiCommandError(ConsumoMaterialiError):
    code = "CONSUMO_MATERIALI_INPUT_INVALID"


class ConsumoMaterialiSeminaNotFoundError(ConsumoMaterialiError):
    code = "CONSUMO_MATERIALI_SEMINA_NOT_FOUND"


class ConsumoMaterialiArticoloNotFoundError(ConsumoMaterialiError):
    code = "CONSUMO_MATERIALI_ARTICOLO_NOT_FOUND"


class ConsumoMaterialiArticoloAmbiguousError(ConsumoMaterialiError):
    code = "CONSUMO_MATERIALI_ARTICOLO_AMBIGUOUS"
