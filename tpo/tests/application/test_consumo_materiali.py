from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.consumo_materiali import (
    ConsumoMaterialiArticoloAmbiguousError, ConsumoMaterialiArticoloNotFoundError,
    ConsumoMaterialiAuthority, ConsumoMaterialiSeminaNotFoundError, ConsumoMaterialiService,
    InvalidConsumoMaterialiCommandError, RegistraConsumoMaterialiSemina, SeminaPerConsumo,
)
from src.tpo_core.application.movimento_articolo.models import (
    RegistraMovimentoArticoloResult,
)
from src.tpo_core.application.movimento_articolo.service import MovimentoArticoloService
from src.tpo_core.domain.identifiers import ActorId, ArticoloId, MovimentoId, SeminaId
from src.tpo_core.domain.states import MovimentoDirection, MovimentoType

AVVIO = datetime(2026, 10, 4, 11, 30, tzinfo=timezone.utc)
AUTH = ConsumoMaterialiAuthority(ActorId("matteo"), "consumo semina", "corr")


class Reader:
    def __init__(self, articoli=None, semine=None):
        self.articoli = articoli if articoli is not None else {
            "vaschette": [ArticoloId("ART-000002")], "substrato": [ArticoloId("ART-000001")]}
        self.semine = semine if semine is not None else {
            "SEM-000021": SeminaPerConsumo(SeminaId("SEM-000021"), "AFI-0410-A", "Afila", AVVIO)}

    def trova_semina(self, semina_id):
        return self.semine.get(semina_id.value)

    def trova_articoli_per_denominazione(self, denominazione):
        return self.articoli.get(denominazione.lower(), [])

    def articolo_esiste(self, articolo_id):
        return any(articolo_id in v for v in self.articoli.values())


class Writer:
    def __init__(self):
        self.commands = []

    def registra(self, command):
        self.commands.append(command)
        return RegistraMovimentoArticoloResult(
            MovimentoId(f"MOV-{len(self.commands):06d}"), command.articolo_id, command.quantita,
            command.unita_misura, command.effective_at, AVVIO, Decimal("100"), "INSERTED")


def service(reader=None):
    writer = Writer()
    return ConsumoMaterialiService(reader or Reader(), MovimentoArticoloService(writer)), writer


def command(**changes):
    values = dict(semina_id=SeminaId("SEM-000021"), set_seminati=7, authority=AUTH)
    values.update(changes)
    return RegistraConsumoMaterialiSemina(**values)


def test_four_pieces_per_set_on_both_articles():
    svc, writer = service()
    result = svc.registra(command())
    assert [c.articolo_id.value for c in writer.commands] == ["ART-000002", "ART-000001"]
    assert all(c.quantita == Decimal("28") and c.unita_misura == "UNIT" for c in writer.commands)
    assert all(c.tipo == MovimentoType.SCARICO and c.direzione == MovimentoDirection.NEGATIVO
               for c in writer.commands)
    assert result.set_seminati == 7 and result.codice_tracciabilita == "AFI-0410-A"


def test_effective_at_defaults_to_semina_start_and_keys_are_derived_from_semina():
    svc, writer = service()
    svc.registra(command())
    assert all(c.effective_at == AVVIO for c in writer.commands)
    keys = [c.authority.idempotency_key for c in writer.commands]
    assert keys == ["consumo-semina-SEM-000021-vaschette", "consumo-semina-SEM-000021-substrato"]


def test_motivo_names_semina_and_set():
    svc, writer = service()
    svc.registra(command())
    assert "SEM-000021" in writer.commands[0].motivo and "7 SET x 4 = 28" in writer.commands[0].motivo


def test_unknown_semina_is_rejected_without_writing():
    svc, writer = service()
    with pytest.raises(ConsumoMaterialiSeminaNotFoundError):
        svc.registra(command(semina_id=SeminaId("SEM-999999")))
    assert writer.commands == []


def test_missing_or_ambiguous_articolo_is_rejected_without_writing():
    svc, writer = service(Reader(articoli={"vaschette": [], "substrato": [ArticoloId("ART-000001")]}))
    with pytest.raises(ConsumoMaterialiArticoloNotFoundError):
        svc.registra(command())
    svc, writer = service(Reader(articoli={
        "vaschette": [ArticoloId("ART-000002"), ArticoloId("ART-000003")],
        "substrato": [ArticoloId("ART-000001")]}))
    with pytest.raises(ConsumoMaterialiArticoloAmbiguousError):
        svc.registra(command())
    assert writer.commands == []


def test_explicit_articoli_override_lookup_and_must_differ():
    svc, writer = service()
    svc.registra(command(articolo_vaschette=ArticoloId("ART-000002"),
                         articolo_substrato=ArticoloId("ART-000001")))
    assert len(writer.commands) == 2
    with pytest.raises(InvalidConsumoMaterialiCommandError):
        svc.registra(command(articolo_vaschette=ArticoloId("ART-000001"),
                             articolo_substrato=ArticoloId("ART-000001")))


@pytest.mark.parametrize("field,value", [("set_seminati", 0), ("set_seminati", -1),
                                         ("pezzi_per_set", 0), ("set_seminati", True)])
def test_non_positive_counts_are_rejected(field, value):
    with pytest.raises(InvalidConsumoMaterialiCommandError):
        command(**{field: value})


def test_naive_effective_at_is_rejected():
    with pytest.raises(InvalidConsumoMaterialiCommandError):
        command(effective_at=datetime(2026, 10, 4, 12))
