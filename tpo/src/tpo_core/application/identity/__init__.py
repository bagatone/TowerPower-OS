"""Policy applicativa per gli identificativi permanenti."""

from .errors import (
    IdentifierSequenceConflictError,
    IdentifierSequenceNotFoundError,
    IdentityAllocationError,
    InvalidIdentifierSequenceError,
)
from .models import AllocatedIdentifier, IdentifierSequence
from .ports import IdentifierSequenceRepository
from .production_planning import (
    PRODUCTION_PLANNING_IDENTIFIER_TYPES,
    PRODUCTION_PLANNING_SEQUENCE_TYPES,
    production_planning_identifier_type,
)
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
    "PRODUCTION_PLANNING_IDENTIFIER_TYPES",
    "PRODUCTION_PLANNING_SEQUENCE_TYPES",
    "production_planning_identifier_type",
)
