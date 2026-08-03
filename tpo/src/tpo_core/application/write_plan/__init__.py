"""Write Plan applicativo immutabile del Tower Power Operations."""

from .errors import (
    DuplicateIdempotencyKeyError,
    DuplicateWritePlanKeyError,
    DuplicateWritePlanRecordError,
    ExistingIdempotencyKeyError,
    InvalidWritePlanError,
    InvalidWriteTargetSnapshotError,
    WritePlanCountMismatchError,
    WritePlanConsistencyError,
    WritePlanError,
    WritePlanRunMismatchError,
    WritePlanValidationError,
    WriteSchemaMismatchError,
    WriteTargetMismatchError,
)
from .models import (
    ValidatedWritePlan,
    WritePlan,
    WritePlanValidationSnapshot,
    WriteTargetSnapshot,
)
from .ports import WritePlanValidationRepository
from .service import WritePlanBuilder
from .validation import (
    WRITE_SCHEMA_ORDINI,
    WRITE_SCHEMA_VERSION,
    WRITE_TARGET_ORDINI,
    WritePlanValidator,
)

__all__ = (
    "DuplicateIdempotencyKeyError",
    "DuplicateWritePlanKeyError",
    "DuplicateWritePlanRecordError",
    "ExistingIdempotencyKeyError",
    "InvalidWritePlanError",
    "InvalidWriteTargetSnapshotError",
    "ValidatedWritePlan",
    "WRITE_SCHEMA_ORDINI",
    "WRITE_SCHEMA_VERSION",
    "WRITE_TARGET_ORDINI",
    "WritePlan",
    "WritePlanBuilder",
    "WritePlanCountMismatchError",
    "WritePlanConsistencyError",
    "WritePlanError",
    "WritePlanRunMismatchError",
    "WritePlanValidationError",
    "WritePlanValidationRepository",
    "WritePlanValidationSnapshot",
    "WritePlanValidator",
    "WriteSchemaMismatchError",
    "WriteTargetMismatchError",
    "WriteTargetSnapshot",
)
