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


class SeminaFinalOutcome(str, Enum):
    RACCOLTA_COMPLETA = "raccolta completa"
    RACCOLTA_PARZIALE_CON_SCARTO = "raccolta parziale con scarto"
    SCARTO_TOTALE = "scarto totale"
    INTERRUZIONE = "interruzione"


class ProgrammaFornituraState(str, Enum):
    ATTIVO = "ATTIVO"
    SOSPESO = "SOSPESO"
    TERMINATO = "TERMINATO"


class OrdineState(str, Enum):
    APERTO = "APERTO"
    PARZIALMENTE_EVASO = "PARZIALMENTE_EVASO"
    EVASO = "EVASO"
    ANNULLATO = "ANNULLATO"


class OrdineCreationType(str, Enum):
    AUTOMATICO = "AUTOMATICO"
    MANUALE = "MANUALE"


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


class SementeRaccomandazione(str, Enum):
    RACCOMANDATA = "RACCOMANDATA"
    UTILIZZABILE = "UTILIZZABILE"
    SCONSIGLIATA = "SCONSIGLIATA"


class ModalitaFatturazione(str, Enum):
    A_CONSEGNA = "A_CONSEGNA"
    PERIODICA_MENSILE = "PERIODICA_MENSILE"
