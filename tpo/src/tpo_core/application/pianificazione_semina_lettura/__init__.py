"""Boundary applicativo "Da seminare" V1 (query a sola lettura, decimo
boundary OPERATIONAL_WEB_ADAPTER -- vedi Fatto 18 della roadmap del
progetto Claude "TPO system")."""

from .errors import (
    InvalidPianificazioneSeminaLetturaQueryError,
    PianificazioneSeminaLetturaError,
)
from .models import (
    STATI_DA_SEMINARE_AMMESSI,
    ElencoDaSeminare,
    RichiediElencoDaSeminare,
    RigaDaSeminare,
)
from .ports import PianificazioneSeminaLetturaReader
from .service import PianificazioneSeminaLetturaService

__all__ = [
    "STATI_DA_SEMINARE_AMMESSI",
    "ElencoDaSeminare",
    "InvalidPianificazioneSeminaLetturaQueryError",
    "PianificazioneSeminaLetturaError",
    "PianificazioneSeminaLetturaReader",
    "PianificazioneSeminaLetturaService",
    "RichiediElencoDaSeminare",
    "RigaDaSeminare",
]
