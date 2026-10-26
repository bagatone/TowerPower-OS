"""Stralcio di righe da un ordine aperto (16/10/2026), su PostgreSQL usa-e-getta. Il CLI e' un registratore."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

from tests.infrastructure.postgresql.test_clandestino_script import _connect
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    _command, _seed, _writer,
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-16_stralcia_riga.py"


def _module():
    spec = importlib.util.spec_from_file_location("stralcia_riga", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ordine_a_due_righe(engine, n):
    """ORD-n del cliente CLI-n: riga 1 = VAR-n (1 SET), riga 2 = VAR-(n+1) (2 SET). Anche ORD-(n+1) a riga singola."""
    _seed(engine, n)
    _seed(engine, n + 1)
    with engine.begin() as connection:
        connection.exec_driver_sql("""
          INSERT INTO tpo.righe_ordine(ordine_id,posizione,varieta_id,quantita,unita_misura,public_id)
          SELECT o.id,2,v.id,2,'SET',%s FROM tpo.ordini o, tpo.varieta v
          WHERE o.public_id=%s AND v.public_id=%s""", (f"RO-{n + 500}", f"ORD-{n:06d}", f"VAR-{n + 1:06d}"))


class Runner:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def __call__(self, cmd):
        self.calls.append(cmd)
        if self.fail:
            return SimpleNamespace(returncode=1, stdout="", stderr="CLI_ERROR")
        return SimpleNamespace(returncode=0, stdout="STATUS: INSERTED\nORDINE_ID=ORD-999001\nCLIENTE_ID=CLI-000011\n", stderr="")


def _go(engine, ordine, righe, esegui=False, runner=None, module=None):
    module, lines = module or _module(), []
    conn = _connect(engine)
    code = module.run(conn, ordine, righe, "il cliente non lo vuole", esegui, out=lines.append,
                      runner=runner or Runner())
    conn.close()
    return code, "\n".join(lines)


def _stato(engine, ordine):
    with engine.connect() as connection:
        return connection.exec_driver_sql("SELECT stato::text FROM tpo.ordini WHERE public_id=%s", (ordine,)).scalar_one()


def test_preview_marks_the_removed_line_and_writes_nothing(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _ordine_a_due_righe(engine, 973001)
    runner = Runner()
    code, text = _go(engine, "ORD-973001", ["Writer variety 973002"], runner=runner)
    assert code == 0 and runner.calls == []
    assert "Writer variety 973002 2 SET   <-- TOLTA" in text and "Writer variety 973001 1 SET" in text
    assert "NUOVO ordine manuale" in text and "ANTEPRIMA: nulla e' stato scritto" in text
    assert _stato(engine, "ORD-973001") == "APERTO"


def test_execute_creates_the_new_order_with_the_kept_lines_then_cancels_the_old(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _ordine_a_due_righe(engine, 973011)
    runner = Runner()
    code, text = _go(engine, "ORD-973011", ["RO-973511"], esegui=True, runner=runner)
    assert code == 0 and "FATTO: ORD-973011 ANNULLATO, sostituito da ORD-999001" in text
    cmd = runner.calls[0]
    assert cmd[1:3] == ["ordine", "registra-manuale"]
    assert cmd[cmd.index("--client") + 1] == "CLI-973011"
    assert cmd[cmd.index("--data-consegna-prevista") + 1] == "2099-01-01"
    righe = [cmd[i + 1] for i, c in enumerate(cmd) if c == "--riga"]
    assert righe == ["VAR-973011:1:SET"]                       # la riga tolta (VAR-973012) non c'e'
    assert cmd[cmd.index("--idempotency-key") + 1].startswith("stralcio-ORD-973011-")
    assert _stato(engine, "ORD-973011") == "ANNULLATO"
    assert _stato(engine, "ORD-973012") == "APERTO"            # l'altro ordine non si tocca
    with engine.connect() as connection:
        reason = connection.exec_driver_sql(
            "SELECT reason FROM tpo.audit_eventi WHERE entity_public_id='ORD-973011' ORDER BY id DESC LIMIT 1").scalar_one()
    assert "sostituito da ORD-999001" in reason and "il cliente non lo vuole" in reason
    assert "COMANDO CORRETTIVO" in text and "annulla ORD-999001" in text


def test_refuses_single_line_all_lines_unknown_line_and_already_delivered(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _ordine_a_due_righe(engine, 973021)
    for ordine, righe, frase in (
            ("ORD-973022", ["Writer variety 973022"], "ha una sola riga"),
            ("ORD-973021", ["Writer variety 973021", "Writer variety 973022"], "TUTTE le righe"),
            ("ORD-973021", ["Inesistente"], "non individua UNA riga"),
            ("ORD-999999", ["x"], "inesistente")):
        runner = Runner()
        code, text = _go(engine, ordine, righe, esegui=True, runner=runner)
        assert code == 2 and frase in text and runner.calls == [], (ordine, righe)
    assert _stato(engine, "ORD-973021") == "APERTO"
    _writer(engine).publish(_command(973022, "0.5", movement=973022))          # consegna parziale di ORD-973022
    code, text = _go(engine, "ORD-973022", ["Writer variety 973022"], esegui=True)
    assert code == 2 and ("PARZIALMENTE_EVASO" in text or "consegne registrate" in text)


def test_cli_failure_leaves_the_old_order_untouched(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _ordine_a_due_righe(engine, 973031)
    code, text = _go(engine, "ORD-973031", ["Writer variety 973032"], esegui=True, runner=Runner(fail=True))
    assert code == 4 and "NON e' stato creato" in text
    assert _stato(engine, "ORD-973031") == "APERTO"


def test_cancel_failure_after_creation_prints_the_compensation(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _ordine_a_due_righe(engine, 973041)
    module = _module()

    def boom(*args, **kwargs):
        raise module.OrderCancellationError("simulato")
    module.cancel = boom
    code, text = _go(engine, "ORD-973041", ["Writer variety 973042"], esegui=True, module=module)
    assert code == 5 and "ORD-999001 ESISTE gia'" in text and "annulla ORD-999001" in text
    assert _stato(engine, "ORD-973041") == "APERTO"
