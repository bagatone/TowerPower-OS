"""Policy applicativa per gli identificativi permanenti."""

from .errors import (
    IdentifierSequenceConflictError,
    IdentifierSequenceNotFoundError,
    IdentityAllocationError,
    InvalidIdentifierSequenceError,
)
from .models import AllocatedIdentifier, IdentifierSequence
from .ports import IdentifierSequenceRepository
from .service import PersistentIdAllocator

__all__ = (
    "AllocatedIdentifier",
    "IdentifierSequence",
    "IdentifierSequenceConflictError",
    "IdentifierSequenceNotFoundError",
    "IdentifierSequenceRepository",
    "IdentityAllocationError",
    "InvalidIdentifierSequenceError",
    "PersistentIdAllocator",
)
