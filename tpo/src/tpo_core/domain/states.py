"""Stati ufficiali congelati del Core Domain."""

from enum import Enum


class VarietaState(str, Enum):
    ATTIVA = "ATTIVA"
    IN_SPERIMENTAZIONE = "IN_SPERIMENTAZIONE"
    SOSPESA = "SOSPESA"
    DISMESSA = "DISMESSA"


class SeminaState(str, Enum):
    AVVIATA = "AVVIATA"
    GERMINAZIONE = "GERMINAZIONE"
    LUCE = "LUCE"
    CRESCITA = "CRESCITA"
    PRONTA_ALLA_RACCOLTA = "PRONTA_ALLA_RACCOLTA"
    CHIUSA = "CHIUSA"


class ProgrammaFornituraState(str, Enum):
    ATTIVO = "ATTIVO"
    SOSPESO = "SOSPESO"
    TERMINATO = "TERMINATO"


class OrdineState(str, Enum):
    APERTO = "APERTO"
    PARZIALMENTE_EVASO = "PARZIALMENTE_EVASO"
    EVASO = "EVASO"
    ANNULLATO = "ANNULLATO"


class ConsegnaState(str, Enum):
    PROGRAMMATA = "PROGRAMMATA"
    IN_PREPARAZIONE = "IN_PREPARAZIONE"
    CONSEGNATA = "CONSEGNATA"
    ANNULLATA = "ANNULLATA"


class MovimentoType(str, Enum):
    CARICO = "CARICO"
    SCARICO = "SCARICO"
    RETTIFICA = "RETTIFICA"


class MovimentoDirection(str, Enum):
    POSITIVO = "POSITIVO"
    NEGATIVO = "NEGATIVO"


class RunState(str, Enum):
    SUCCESS = "SUCCESS"
    SUCCESS_WITH_WARNINGS = "SUCCESS_WITH_WARNINGS"
    FAILED = "FAILED"
