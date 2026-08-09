"""Exit code congelati del comando CLI operativo."""

from enum import IntEnum


class OperationalExitCode(IntEnum):
    OPERATION_COMMITTED = 0
    OPERATION_FAILED = 1
    OPERATION_INPUT_INVALID = 2
    OPERATION_RUNTIME_UNAVAILABLE = 3
    OPERATION_RECONCILIATION_REQUIRED = 4
    OPERATION_INTERNAL_ERROR = 5
