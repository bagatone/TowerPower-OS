"""Policy applicativa per gli identificativi permanenti."""

from .errors import (
    IdentifierSequenceConflictError,
    IdentifierSequenceNotFoundError,
    IdentityAllocationError,
    InvalidIdentifierSequenceError,
    IdentityCommissioningConflictError,
    IdentityCommissioningError,
    IdentityCommissioningOutcomeUncertain,
    IdentityCommissioningPersistenceError,
    InvalidIdentityCommissioningCommandError,
)
from .models import (
    AllocatedIdentifier,
    CommissionedIdentityRegistration,
    CommissionIdentityRegistration,
    IdentifierSequence,
)
from .ports import IdentityRegistrationCommissioningWriter, IdentifierSequenceRepository
from .production_planning import (
    PRODUCTION_PLANNING_IDENTIFIER_TYPES,
    PRODUCTION_PLANNING_SEQUENCE_TYPES,
    production_planning_identifier_type,
)
from .service import IdentityRegistrationCommissioningService, PersistentIdAllocator

__all__ = (
    "AllocatedIdentifier",
    "IdentifierSequence",
    "IdentifierSequenceConflictError",
    "IdentifierSequenceNotFoundError",
    "IdentifierSequenceRepository",
    "IdentityRegistrationCommissioningWriter",
    "CommissionIdentityRegistration",
    "CommissionedIdentityRegistration",
    "IdentityRegistrationCommissioningService",
    "IdentityCommissioningError",
    "IdentityCommissioningConflictError",
    "IdentityCommissioningPersistenceError",
    "IdentityCommissioningOutcomeUncertain",
    "InvalidIdentityCommissioningCommandError",
    "IdentityAllocationError",
    "InvalidIdentifierSequenceError",
    "PersistentIdAllocator",
    "PRODUCTION_PLANNING_IDENTIFIER_TYPES",
    "PRODUCTION_PLANNING_SEQUENCE_TYPES",
    "production_planning_identifier_type",
)
