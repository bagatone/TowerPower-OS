"""Errori applicativi della tracciabilità delle RUN."""


class RunTrackingError(RuntimeError):
    """Errore base della tracciabilità applicativa."""


class InvalidSchedulingRunError(RunTrackingError, ValueError):
    """RUN incoerente o non valida."""


class SchedulingRunAlreadyExistsError(RunTrackingError):
    """Il RunId risulta già registrato."""


class SchedulingRunNotFoundError(RunTrackingError):
    """Il RunId non risulta registrato."""


class SchedulingRunConflictError(RunTrackingError):
    """La RUN non è più aperta o la sua versione è cambiata."""
