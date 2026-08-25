from typing import Protocol
from .models import TransitionSemina, TransitionSeminaResult


class SeminaLifecycleWriter(Protocol):
    def transition(self, command: TransitionSemina) -> TransitionSeminaResult: ...
