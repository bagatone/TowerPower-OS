"""Protocollo applicativo di preparazione del commit."""

from .errors import (
    CommitError,
    CommitExecutionError,
    CommitExistingKeyError,
    CommitPreparationError,
    CommitReceiptMismatchError,
    CommitSchemaChangedError,
    CommitSerializationError,
    InvalidCommitRequestError,
)
from .models import (
    CommitExecutionReceipt,
    CommitOutcomeUncertain,
    CommitRequest,
    CommitResult,
    CommitStatus,
)
from .context import CommitExecutionContext
from .ports import CommitRepository
from .service import ApplicationCommitter

__all__ = (
    "ApplicationCommitter",
    "CommitError",
    "CommitExecutionError",
    "CommitExecutionReceipt",
    "CommitOutcomeUncertain",
    "CommitExecutionContext",
    "CommitExistingKeyError",
    "CommitPreparationError",
    "CommitReceiptMismatchError",
    "CommitRepository",
    "CommitRequest",
    "CommitResult",
    "CommitStatus",
    "CommitSchemaChangedError",
    "CommitSerializationError",
    "InvalidCommitRequestError",
)
