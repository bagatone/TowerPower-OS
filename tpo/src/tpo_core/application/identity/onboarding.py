"""Frozen public Identity registrations required by operational onboarding."""

from ...domain.identifiers import ClienteId, ProgrammaFornituraId, VarietaId

ONBOARDING_SEQUENCE_TYPES = {
    ClienteId.sequence_name: ClienteId,
    VarietaId.sequence_name: VarietaId,
    ProgrammaFornituraId.sequence_name: ProgrammaFornituraId,
}
