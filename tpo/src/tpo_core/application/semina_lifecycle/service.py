from .errors import InvalidSeminaLifecycleCommandError
from .models import TransitionSemina, TransitionSeminaResult
from .ports import SeminaLifecycleWriter


class SeminaLifecycleService:
    def __init__(self, writer: SeminaLifecycleWriter) -> None:
        self._writer = writer

    def transition(self, command: TransitionSemina) -> TransitionSeminaResult:
        if not isinstance(command, TransitionSemina):
            raise InvalidSeminaLifecycleCommandError("command non valido.")
        return self._writer.transition(command)
