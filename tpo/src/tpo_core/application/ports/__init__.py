"""Porte astratte dell'Application Layer."""

from .clock import Clock
from .repositories import OrdineRepository, ProgrammaFornituraRepository

__all__ = ["Clock", "OrdineRepository", "ProgrammaFornituraRepository"]
