from datetime import date, datetime, timezone

import pytest

from src.tpo_core.application.programma_fornitura_sospensione.errors import (
    InvalidProgrammaFornituraSospensioneCommandError,
)
from src.tpo_core.application.programma_fornitura_sospensione.models import (
    ProgrammaFornituraSospensioneAuthority, RiattivaProgrammaFornitura,
    SospendiProgrammaFornitura,
)
from src.tpo_core.application.programma_fornitura_sospensione.service import (
    ProgrammaFornituraSospensioneService,
)
from src.tpo_core.domain.identifiers import ActorId, ProgrammaFornituraId


AUTH = ProgrammaFornituraSospensioneAuthority(
    ActorId("owner"), "finestra clienti chiusi", "corr-1", "idem-1"
)
EFFECTIVE_AT = datetime(2026, 9, 16, 8, tzinfo=timezone.utc)


def sospendi(**changes):
    values = dict(
        programma_id=ProgrammaFornituraId("PF-000001"),
        expected_numero_versione=1,
        effective_at=EFFECTIVE_AT,
        authority=AUTH,
    )
    values.update(changes)
    return SospendiProgrammaFornitura(**values)


def riattiva(**changes):
    values = dict(
        programma_id=ProgrammaFornituraId("PF-000001"),
        expected_numero_versione=2,
        effective_at=EFFECTIVE_AT,
        authority=AUTH,
    )
    values.update(changes)
    return RiattivaProgrammaFornitura(**values)


def test_sospendi_valido_senza_data_ripresa():
    command = sospendi()
    assert command.data_ripresa_prevista is None
    assert command.effective_at.tzinfo is timezone.utc
    assert len(command.canonical_payload_hash) == 64


def test_sospendi_valido_con_data_ripresa():
    command = sospendi(data_ripresa_prevista=date(2026, 10, 1))
    assert command.data_ripresa_prevista == date(2026, 10, 1)


def test_sospendi_data_ripresa_deve_essere_date():
    with pytest.raises(InvalidProgrammaFornituraSospensioneCommandError):
        sospendi(data_ripresa_prevista="2026-10-01")
    with pytest.raises(InvalidProgrammaFornituraSospensioneCommandError):
        sospendi(data_ripresa_prevista=datetime(2026, 10, 1, tzinfo=timezone.utc))


@pytest.mark.parametrize("versione", [0, -1, 1.5, True, "1", None])
def test_sospendi_expected_numero_versione_deve_essere_intero_positivo(versione):
    with pytest.raises(InvalidProgrammaFornituraSospensioneCommandError):
        sospendi(expected_numero_versione=versione)


def test_sospendi_effective_at_deve_essere_aware():
    with pytest.raises(InvalidProgrammaFornituraSospensioneCommandError):
        sospendi(effective_at=datetime(2026, 9, 16, 8))


def test_sospendi_programma_id_tipizzato():
    with pytest.raises(InvalidProgrammaFornituraSospensioneCommandError):
        sospendi(programma_id="PF-000001")


def test_sospendi_distinct_payloads_hash_differently():
    base = sospendi()
    other_version = sospendi(expected_numero_versione=2)
    other_date = sospendi(data_ripresa_prevista=date(2026, 10, 1))
    other_effective = sospendi(effective_at=datetime(2026, 9, 17, 8, tzinfo=timezone.utc))
    assert base.canonical_payload_hash != other_version.canonical_payload_hash
    assert base.canonical_payload_hash != other_date.canonical_payload_hash
    assert base.canonical_payload_hash != other_effective.canonical_payload_hash


def test_riattiva_valido():
    command = riattiva()
    assert command.expected_numero_versione == 2
    assert len(command.canonical_payload_hash) == 64


@pytest.mark.parametrize("versione", [0, -1, 1.5, True])
def test_riattiva_expected_numero_versione_deve_essere_intero_positivo(versione):
    with pytest.raises(InvalidProgrammaFornituraSospensioneCommandError):
        riattiva(expected_numero_versione=versione)


def test_riattiva_effective_at_deve_essere_aware():
    with pytest.raises(InvalidProgrammaFornituraSospensioneCommandError):
        riattiva(effective_at=datetime(2026, 9, 16, 8))


def test_riattiva_distinct_payloads_hash_differently():
    base = riattiva()
    other = riattiva(expected_numero_versione=3)
    assert base.canonical_payload_hash != other.canonical_payload_hash


def test_sospendi_e_riattiva_hash_non_si_confondono():
    # Stessi identici parametri logici, boundary diversi: non devono mai collidere.
    s = SospendiProgrammaFornitura(
        ProgrammaFornituraId("PF-000001"), 1, EFFECTIVE_AT, AUTH,
    )
    r = RiattivaProgrammaFornitura(
        ProgrammaFornituraId("PF-000001"), 1, EFFECTIVE_AT, AUTH,
    )
    assert s.canonical_payload_hash != r.canonical_payload_hash


def test_authority_richiede_campi_testuali_normalizzati():
    with pytest.raises(InvalidProgrammaFornituraSospensioneCommandError):
        ProgrammaFornituraSospensioneAuthority(ActorId("owner"), "", "corr", "idem")
    with pytest.raises(InvalidProgrammaFornituraSospensioneCommandError):
        ProgrammaFornituraSospensioneAuthority(ActorId("owner"), "reason", " corr ", "idem")


def test_authority_richiede_actor_id_tipizzato():
    with pytest.raises(InvalidProgrammaFornituraSospensioneCommandError):
        ProgrammaFornituraSospensioneAuthority("owner", "reason", "corr", "idem")


def test_service_sospendi_e_riattiva_sono_thin_e_tipizzati():
    class Writer:
        def sospendi(self, command):
            assert command == sospendi()
            return "sospeso"

        def riattiva(self, command):
            assert command == riattiva()
            return "riattivato"

    service = ProgrammaFornituraSospensioneService(Writer())
    assert service.sospendi(sospendi()) == "sospeso"
    assert service.riattiva(riattiva()) == "riattivato"
    with pytest.raises(InvalidProgrammaFornituraSospensioneCommandError):
        service.sospendi(object())
    with pytest.raises(InvalidProgrammaFornituraSospensioneCommandError):
        service.riattiva(object())
