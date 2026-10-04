"""Boundary applicativo CONSUMO_MATERIALI_SEMINA V1."""

from .errors import (
    ConsumoMaterialiArticoloAmbiguousError,
    ConsumoMaterialiArticoloNotFoundError,
    ConsumoMaterialiError,
    ConsumoMaterialiSeminaNotFoundError,
    InvalidConsumoMaterialiCommandError,
)
from .models import (
    ConsumoMaterialiAuthority,
    PEZZI_PER_SET_DEFAULT,
    RegistraConsumoMaterialiSemina,
    RegistraConsumoMaterialiSeminaResult,
    SeminaPerConsumo,
)
from .ports import ConsumoMaterialiReader
from .service import ConsumoMaterialiService

__all__ = [
    "ConsumoMaterialiArticoloAmbiguousError", "ConsumoMaterialiArticoloNotFoundError",
    "ConsumoMaterialiAuthority", "ConsumoMaterialiError", "ConsumoMaterialiReader",
    "ConsumoMaterialiSeminaNotFoundError", "ConsumoMaterialiService",
    "InvalidConsumoMaterialiCommandError", "PEZZI_PER_SET_DEFAULT",
    "RegistraConsumoMaterialiSemina", "RegistraConsumoMaterialiSeminaResult",
    "SeminaPerConsumo",
]
