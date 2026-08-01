"""Entità del Core Domain."""

from .consegna import Consegna, RigaConsegna
from .movimento_magazzino import MovimentoMagazzino
from .ordine import Ordine, PrenotazioneOrdine, RigaOrdine
from .programma_fornitura import (
    ConfigurazioneTemporale,
    ProgrammaFornitura,
    RigaProgrammaFornitura,
    TipoRicorrenza,
)
from .raccolta import Raccolta
from .semina import Semina
from .stock import Stock
from .varieta import Varieta

__all__ = [
    "ConfigurazioneTemporale",
    "Consegna",
    "MovimentoMagazzino",
    "Ordine",
    "PrenotazioneOrdine",
    "ProgrammaFornitura",
    "Raccolta",
    "RigaConsegna",
    "RigaProgrammaFornitura",
    "RigaOrdine",
    "Semina",
    "Stock",
    "TipoRicorrenza",
    "Varieta",
]
