"""Bridge Identity tipizzato per il boundary Production Planning."""

from __future__ import annotations

from ...application.identity.production_planning import (
    production_planning_identifier_type,
)
from ...application.identity.service import PersistentIdAllocator
from ...application.production_planning.models import PublicId


class PostgreSQLProductionPlanningIdentityAdapter:
    """Adatta sequence name Planning allo stack Identity PostgreSQL esistente."""

    def __init__(self, allocator: PersistentIdAllocator) -> None:
        if not isinstance(allocator, PersistentIdAllocator):
            raise TypeError("allocator deve essere PersistentIdAllocator.")
        self._allocator = allocator

    def allocate(self, sequence_name: str) -> PublicId:
        identifier_type = production_planning_identifier_type(sequence_name)
        allocated = self._allocator.allocate(identifier_type)
        return PublicId(allocated.identifier.value)
