"""Walkthrough CLI end-to-end su un cluster PostgreSQL locale, isolato e usa-e-getta.

Perche' questo script esiste
-----------------------------
Ogni boundary di TPO (SEMENTE, SEMENTE_IMPIEGO, LOTTO_SEME, SEMINA, RACCOLTA,
MOVIMENTO_MAGAZZINO, ASSEGNAZIONE_FISICA, CONSEGNA, FATTURA, INCASSO, ...) e'
gia' verificato singolarmente da `pytest` (dominio, applicazione, PostgreSQL
reale). Quello che NON e' mai stato dimostrato in un colpo solo e' che la
catena intera funzioni insieme, esattamente come la userebbe un operatore
reale dalla riga di comando: cliente -> ordine -> semente -> lotto seme ->
semina -> raccolta -> carico a magazzino -> consegna -> assegnazione fisica
-> fattura -> incasso.

Questo script esegue quella catena chiamando il VERO binario CLI di
produzione (`python -m src.tpo_core.cli.main ...`, lo stesso eseguito in
produzione), passo per passo, stampando ogni comando e il suo output reale,
su un database PostgreSQL completamente isolato e temporaneo (mai il
database reale configurato in .env.local/Supabase): un cluster PostgreSQL
disponibile viene avviato in una directory temporanea, con un database
usa-e-getta, migrato a head con Alembic, e distrutto a fine esecuzione
(a meno di --keep).

Cosa NON e' ancora esposto da CLI e viene quindi seminato via SQL direttamente
(dati di riferimento, non scritture governate da un boundary applicativo):
nomenclatura di CULTIVAR/USO_PRODUTTIVO/PROTOCOLLO/PROTOCOLLO_VERSIONE, e
l'ORDINE/RIGA_ORDINE del cliente (l'acquisizione ordini e' oggi fuori
mandato scritto di TPO: nessun comando CLI la espone, si veda
AUTHORITY_REGISTRY.yaml). Tutto il resto della catena passa dalla CLI reale.

Uso:
    .venv/bin/python scripts/walkthrough/e2e_walkthrough.py
    .venv/bin/python scripts/walkthrough/e2e_walkthrough.py --keep

Con --keep il cluster disponibile resta attivo a fine esecuzione (o in caso
di errore) per ispezione manuale con psql; lo script stampa la stringa di
connessione e il comando per fermarlo quando non serve piu'.

Requisiti sulla macchina da cui si esegue: PostgreSQL client+server binaries
(`initdb`, `pg_ctl`) e `openssl` sul PATH, oltre al virtualenv di progetto
gia' creato (`./bootstrap.sh`).
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
CLI_MODULE = "src.tpo_core.cli.main"

sys.path.insert(0, str(ROOT))

# Namespace dedicato di identita' di prova: numerazione riservata (95xxxx) per
# non rischiare mai di collidere con altri dati, anche se il database e'
# comunque nuovo e isolato ad ogni esecuzione.
CLI_ID = "CLI-950001"
VAR_ID = "VAR-950001"
ORD_ID = "ORD-950001"
RO_ID = "RO-950001"
PV_ID = "PV-950001"
SEED_FORNITORE = "Vivaio Walkthrough"
SEED_REFERENZA = "WLK-SEED-1"
RIGA_QUANTITA = "500"
RIGA_UOM = "GRAM"

BASE = datetime(2026, 8, 21, 8, 0, tzinfo=timezone.utc)

_STEP = [0]


class WalkthroughError(RuntimeError):
    pass


def log(msg: str = "") -> None:
    print(msg, flush=True)


def header(title: str) -> None:
    _STEP[0] += 1
    log()
    log("=" * 78)
    log(f"STEP {_STEP[0]}: {title}")
    log("=" * 78)


def note(msg: str) -> None:
    log(f"  # {msg}")


def parse_fields(stdout: str) -> dict:
    fields: dict[str, str] = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        eq = line.find("=")
        colon = line.find(": ")
        if eq != -1 and (colon == -1 or eq < colon):
            key, _, value = line.partition("=")
        elif colon != -1:
            key, _, value = line.partition(": ")
        else:
            continue
        fields[key.strip()] = value.strip()
    return fields


def run_cli(argv: list, env: dict, *, expect_ok: bool = True) -> tuple:
    display = " ".join(shlex.quote(a) for a in argv)
    log(f"$ tpo {display}")
    completed = subprocess.run(
        [str(VENV_PYTHON), "-m", CLI_MODULE, *argv],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=60,
    )
    if completed.stdout:
        log(completed.stdout.rstrip())
    if completed.stderr:
        log(completed.stderr.rstrip())
    if expect_ok and completed.returncode != 0:
        raise WalkthroughError(
            f"Comando fallito (exit {completed.returncode}): tpo {display}"
        )
    return parse_fields(completed.stdout), completed


# --------------------------------------------------------------------------
# Cluster PostgreSQL disponibile e isolato (stessa tecnica della fixture
# `isolated_postgresql` in tests/infrastructure/postgresql/
# test_production_planning_migrations.py, con l'aggiunta di TLS
# self-signed: le impostazioni di produzione (PostgreSQLSettings) accettano
# solo sslmode in {require, verify-ca, verify-full}, per coerenza con
# Supabase).
# --------------------------------------------------------------------------

def free_tcp_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def start_cluster(root: Path) -> dict:
    initdb = shutil.which("initdb")
    pg_ctl = shutil.which("pg_ctl")
    openssl = shutil.which("openssl")
    missing = [name for name, path in
               (("initdb", initdb), ("pg_ctl", pg_ctl), ("openssl", openssl))
               if path is None]
    if missing:
        raise WalkthroughError(
            "Binari mancanti sul PATH: " + ", ".join(missing) + ". "
            "Installa PostgreSQL (es. `brew install postgresql@16`, poi "
            "aggiungi il suo bin/ al PATH) e assicurati che `openssl` sia "
            "disponibile (di serie su macOS)."
        )
    data = root / "data"
    log_file = root / "postgres.log"
    env = {**os.environ, "LC_ALL": "C"}

    initialized = subprocess.run(
        [initdb, "-D", str(data), "--auth=trust", "--username=postgres", "--encoding=UTF8"],
        capture_output=True, text=True, env=env,
    )
    if initialized.returncode:
        raise WalkthroughError(f"initdb fallito: {initialized.stderr.strip()}")

    cert = data / "server.crt"
    key = data / "server.key"
    made_cert = subprocess.run(
        [openssl, "req", "-new", "-x509", "-days", "3650", "-nodes",
         "-subj", "/CN=localhost", "-keyout", str(key), "-out", str(cert)],
        capture_output=True, text=True,
    )
    if made_cert.returncode:
        raise WalkthroughError(
            f"Generazione del certificato TLS self-signed fallita: {made_cert.stderr.strip()}"
        )
    os.chmod(key, 0o600)

    port = free_tcp_port()
    options = (
        f"-F -p {port} -h 127.0.0.1 "
        f"-c ssl=on -c ssl_cert_file={cert} -c ssl_key_file={key}"
    )
    started = subprocess.run(
        [pg_ctl, "-D", str(data), "-l", str(log_file), "-o", options, "-w", "start"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    if started.returncode:
        server_log = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else ""
        raise WalkthroughError(
            f"Avvio del cluster PostgreSQL disponibile fallito: {started.stderr.strip()}\n"
            f"postgres.log:\n{server_log}"
        )
    log(f"Cluster PostgreSQL disponibile avviato su 127.0.0.1:{port} "
        f"(TLS self-signed, isolato). Data dir: {data}")
    return {"data": data, "port": port, "pg_ctl": pg_ctl, "env": env, "log_file": log_file}


def stop_cluster(cluster: dict) -> None:
    subprocess.run(
        [cluster["pg_ctl"], "-D", str(cluster["data"]), "-m", "fast", "-w", "stop"],
        capture_output=True, text=True, env=cluster["env"], timeout=30, check=False,
    )


def create_database_and_migrate(cluster: dict, dbname: str):
    import sqlalchemy as sa
    from alembic import command as alembic_command

    from src.tpo_core.infrastructure.postgresql.alembic import make_config

    admin_url = f"postgresql+psycopg://postgres@127.0.0.1:{cluster['port']}/postgres?sslmode=require"
    admin_engine = sa.create_engine(admin_url)
    try:
        with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{dbname}"')
    finally:
        admin_engine.dispose()

    db_url = f"postgresql+psycopg://postgres@127.0.0.1:{cluster['port']}/{dbname}?sslmode=require"
    engine = sa.create_engine(db_url)
    with engine.begin() as connection:
        alembic_command.upgrade(make_config(connection=connection), "head")
    return engine


def cli_environment(cluster: dict, dbname: str) -> dict:
    env = os.environ.copy()
    for key in (
        "TPO_DATABASE_HOST", "TPO_DATABASE_PORT", "TPO_DATABASE_NAME",
        "TPO_DATABASE_USER", "TPO_DATABASE_PASSWORD", "TPO_DATABASE_SSLMODE",
        "TPO_DATABASE_CONNECT_TIMEOUT",
    ):
        env.pop(key, None)
    env.update({
        "TPO_DATABASE_HOST": "127.0.0.1",
        "TPO_DATABASE_PORT": str(cluster["port"]),
        "TPO_DATABASE_NAME": dbname,
        "TPO_DATABASE_USER": "postgres",
        "TPO_DATABASE_PASSWORD": "walkthrough",
        "TPO_DATABASE_SSLMODE": "require",
        "TPO_DATABASE_CONNECT_TIMEOUT": "10",
    })
    return env


# --------------------------------------------------------------------------
# Dati di riferimento non ancora esposti da CLI (seminati via SQL diretto,
# stessi valori gia' verificati da tests/integration/postgresql/
# test_semina_commissioning.py e tests/infrastructure/postgresql/
# test_production_planning_commit_writer.py::_seed_authorities).
# --------------------------------------------------------------------------

def seed_protocol_reference_data(engine, *, varieta_public_id: str, protocol_public_id: str) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(f"""
        INSERT INTO tpo.cultivar (varieta_id,denominazione,stato,created_by,updated_at,updated_by)
        SELECT id,'Afila Walkthrough','ATTIVA','walkthrough',CURRENT_TIMESTAMP,'walkthrough'
        FROM tpo.varieta WHERE public_id='{varieta_public_id}';

        INSERT INTO tpo.usi_produttivi (codice,denominazione,created_by,updated_at,updated_by)
        VALUES ('MICROGREEN','Microgreen','walkthrough',CURRENT_TIMESTAMP,'walkthrough');

        INSERT INTO tpo.cultivar_usi (cultivar_id,uso_produttivo_id,stato_validazione,created_by,updated_at,updated_by)
        SELECT c.id,u.id,'APPROVATA','walkthrough',CURRENT_TIMESTAMP,'walkthrough'
        FROM tpo.cultivar c CROSS JOIN tpo.usi_produttivi u
        WHERE c.denominazione='Afila Walkthrough' AND u.codice='MICROGREEN';

        INSERT INTO tpo.protocolli (cultivar_uso_id,tipo,denominazione,created_by,updated_at,updated_by)
        SELECT id,'STANDARD','Protocollo Walkthrough','walkthrough',CURRENT_TIMESTAMP,'walkthrough'
        FROM tpo.cultivar_usi;

        INSERT INTO tpo.protocollo_versioni
          (public_id,protocollo_id,numero_versione,valida_dal,contenuto,motivazione,
           stato_approvazione,idratazione_ore,orario_semina_previsto,
           orario_raccolta_target,germinazione_giorni,crescita_luce_giorni,
           grammi_seme_per_set,resa_attesa,resa_unita_misura,
           granularita_produttiva,harvest_min_lead_giorni,
           harvest_max_lead_giorni,buffer_temporale_minuti,provenance,
           approvata_at,approvata_by,created_by)
        SELECT '{protocol_public_id}',id,1,DATE '2026-01-01','walkthrough','walkthrough','APPROVATA',
               8,TIME '06:00',TIME '06:00',2,7,25,1,'SET',0.5,1,2,0,
               'approved-protocol-walkthrough',CURRENT_TIMESTAMP,'walkthrough','walkthrough'
        FROM tpo.protocolli WHERE denominazione='Protocollo Walkthrough';
        """)
    note(f"Seminati (SQL diretto): cultivar/uso produttivo/protocollo/{protocol_public_id} "
         f"per {varieta_public_id} (nomenclatura oggi non esposta da CLI).")


def seed_order(engine, *, cliente_public_id: str, varieta_public_id: str,
                ordine_public_id: str, riga_public_id: str,
                quantita: str, unita_misura: str) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(f"""
        INSERT INTO tpo.ordini
          (public_id,cliente_id,data_ordine,data_consegna_prevista,stato,tipo_creazione,created_by,version)
        SELECT '{ordine_public_id}',id,DATE '2026-08-20',DATE '2026-09-10','APERTO','MANUALE','walkthrough',0
        FROM tpo.clienti WHERE public_id='{cliente_public_id}';

        INSERT INTO tpo.righe_ordine (public_id,ordine_id,posizione,varieta_id,quantita,unita_misura,version)
        SELECT '{riga_public_id}',o.id,1,v.id,{quantita},'{unita_misura}',0
        FROM tpo.ordini o CROSS JOIN tpo.varieta v
        WHERE o.public_id='{ordine_public_id}' AND v.public_id='{varieta_public_id}';
        """)
    note(f"Seminati (SQL diretto): {ordine_public_id}/{riga_public_id} per {cliente_public_id} "
         f"({quantita} {unita_misura} di {varieta_public_id}) - l'acquisizione ordini e' oggi "
         f"fuori mandato scritto di TPO, nessun comando CLI la espone.")


def final_trace(engine, *, cliente_public_id: str) -> list:
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(f"""
        SELECT
          cl.public_id AS cliente,
          o.public_id AS ordine, o.stato AS ordine_stato,
          ro.public_id AS riga_ordine, ro.quantita AS riga_quantita, ro.unita_misura AS riga_uom,
          af.public_id AS assegnazione_fisica, af.quantita_assegnata,
          rac.public_id AS raccolta, rac.quantita AS raccolta_quantita,
          sem.public_id AS semina, sem.stato AS semina_stato,
          con.public_id AS consegna, con.stato AS consegna_stato,
          f.numero_fattura, f.totale,
          inc.public_id AS incasso, inc.importo
        FROM tpo.clienti cl
        JOIN tpo.ordini o ON o.cliente_id = cl.id
        JOIN tpo.righe_ordine ro ON ro.ordine_id = o.id
        LEFT JOIN tpo.assegnazioni_fisiche af ON af.riga_ordine_id = ro.id
        LEFT JOIN tpo.raccolte rac ON rac.id = af.raccolta_id
        LEFT JOIN tpo.semine sem ON sem.id = rac.semina_id
        LEFT JOIN tpo.righe_consegna rc ON rc.riga_ordine_id = ro.id
        LEFT JOIN tpo.consegne con ON con.id = rc.consegna_id
        LEFT JOIN tpo.fatture_consegne fc ON fc.consegna_id = con.id
        LEFT JOIN tpo.fatture f ON f.id = fc.fattura_id
        LEFT JOIN tpo.incassi inc ON inc.fattura_numero = f.numero_fattura
        WHERE cl.public_id = '{cliente_public_id}'
        """).mappings().all()
    return [dict(row) for row in rows]


def commission_identity(env: dict, permanent_id_type) -> None:
    """Commissiona una identita' ALLOCATA (SEM/LSE/...) prima del suo primo uso.

    Non tutte le identita' pubbliche sono seminate da una migrazione (RAC,
    MOV, CON, INC, USC, ART, ASF lo sono gia', direttamente nella loro
    migrazione di introduzione): alcune richiedono un'autorizzazione
    esplicita, una tantum, prima che un writer possa allocarne la prima
    istanza - stesso identico passo eseguito dalle fixture di integrazione
    reali (es. tests/integration/postgresql/test_seed_lot_commissioning.py
    e tests/integration/postgresql/test_semina_commissioning.py) prima di
    esercitare LOTTO_SEME_ID/SEMINA_ID su un database nuovo.
    """
    from src.tpo_core.application.identity import CommissionIdentityRegistration
    from src.tpo_core.bootstrap import build_identity_registration_commissioner
    from src.tpo_core.domain.identifiers import ActorId
    from src.tpo_core.infrastructure.postgresql.settings import PostgreSQLSettings

    settings = PostgreSQLSettings.from_environment(env)
    service = build_identity_registration_commissioner(settings)
    service.commission(CommissionIdentityRegistration(
        permanent_id_type.sequence_name, permanent_id_type, permanent_id_type.prefix,
        ActorId("walkthrough-identity"),
    ))
    note(f"Identita' {permanent_id_type.sequence_name} commissionata (una tantum).")


def check_disponibilita_commerciale(env: dict, *, varieta_public_id: str):
    from src.tpo_core.application.disponibilita_commerciale import (
        RichiediDisponibilitaCommerciale,
    )
    from src.tpo_core.bootstrap import build_disponibilita_commerciale_service
    from src.tpo_core.domain.identifiers import VarietaId
    from src.tpo_core.infrastructure.postgresql.settings import PostgreSQLSettings

    settings = PostgreSQLSettings.from_environment(env)
    service = build_disponibilita_commerciale_service(settings)
    return service.disponibilita(RichiediDisponibilitaCommerciale(VarietaId(varieta_public_id)))


# --------------------------------------------------------------------------
# Catena end-to-end
# --------------------------------------------------------------------------

def run_chain(env: dict, engine) -> None:
    header(f"Onboarding CLIENTE {CLI_ID} (tpo onboarding customer)")
    run_cli([
        "onboarding", "customer",
        "--customer-id", CLI_ID, "--denomination", "Cliente Walkthrough",
        "--actor", "walkthrough", "--reason", "Walkthrough end-to-end",
        "--correlation-id", "wlk-customer",
    ], env)

    header(f"Onboarding VARIETA {VAR_ID} (tpo onboarding variety)")
    run_cli([
        "onboarding", "variety",
        "--variety-id", VAR_ID, "--denomination", "Varieta Walkthrough",
        "--traceability-code", "WLK", "--state", "ATTIVA",
        "--actor", "walkthrough", "--reason", "Walkthrough end-to-end",
        "--correlation-id", "wlk-variety",
    ], env)

    header("Dati di riferimento oggi non esposti da CLI (protocollo/cultivar, ordine/riga ordine)")
    seed_protocol_reference_data(engine, varieta_public_id=VAR_ID, protocol_public_id=PV_ID)
    seed_order(engine, cliente_public_id=CLI_ID, varieta_public_id=VAR_ID,
               ordine_public_id=ORD_ID, riga_public_id=RO_ID,
               quantita=RIGA_QUANTITA, unita_misura=RIGA_UOM)

    header("Commissioning delle identita' allocate SEMINA_ID/LOTTO_SEME_ID (una tantum)")
    from src.tpo_core.domain.identifiers import LottoSemeId, SeminaId
    commission_identity(env, LottoSemeId)
    commission_identity(env, SeminaId)

    header(f"Prezzo di listino per {VAR_ID} (tpo listino-varieta set)")
    run_cli([
        "listino-varieta", "set",
        "--varieta", VAR_ID, "--prezzo-unitario", "0.045", "--aliquota-igic", "7.00",
        "--actor", "walkthrough", "--reason", "Walkthrough end-to-end",
        "--correlation-id", "wlk-listino",
    ], env)

    header(f"Configurazione di fatturazione per {CLI_ID} (tpo cliente fatturazione)")
    run_cli([
        "cliente", "fatturazione",
        "--client", CLI_ID, "--modalita-fatturazione", "A_CONSEGNA",
        "--termini-pagamento-giorni", "30", "--actor", "walkthrough",
    ], env)

    header("Commissioning SEMENTE (tpo semente commission)")
    run_cli([
        "semente", "commission",
        "--fornitore", SEED_FORNITORE, "--referenza-commerciale", SEED_REFERENZA,
        "--actor", "walkthrough", "--reason", "Walkthrough end-to-end",
        "--correlation-id", "wlk-semente", "--idempotency-key", "wlk-semente-1",
        "--confirm",
    ], env)

    header("Commissioning SEMENTE_IMPIEGO (tpo semente-impiego commission)")
    run_cli([
        "semente-impiego", "commission",
        "--fornitore", SEED_FORNITORE, "--referenza-commerciale", SEED_REFERENZA,
        "--protocol-version", PV_ID, "--raccomandazione", "RACCOMANDATA",
        "--actor", "walkthrough", "--reason", "Walkthrough end-to-end",
        "--correlation-id", "wlk-semente-impiego", "--idempotency-key", "wlk-semente-impiego-1",
        "--confirm",
    ], env)

    header("Commissioning LOTTO_SEME (tpo seed-lot commission)")
    seed_lot_provenance = json.dumps({
        "seed_supplier": "OWNER_AUTHORIZED", "seed_commercial_reference": "OWNER_AUTHORIZED",
        "manufacturer_lot_number": "OWNER_AUTHORIZED", "received_date": "OWNER_AUTHORIZED",
        "expiry_date": "UNKNOWN", "initial_quantity": "OWNER_AUTHORIZED",
        "unit": "OWNER_AUTHORIZED", "anomaly": "UNKNOWN",
    })
    fields, _ = run_cli([
        "seed-lot", "commission",
        "--seed-supplier", SEED_FORNITORE, "--seed-commercial-reference", SEED_REFERENZA,
        "--manufacturer-lot-number", "LOTTO-WLK-1", "--received-date", "2026-08-20",
        "--initial-quantity", "50", "--unit", "GRAM", "--provenance", seed_lot_provenance,
        "--actor", "walkthrough", "--reason", "Walkthrough end-to-end",
        "--correlation-id", "wlk-seed-lot", "--idempotency-key", "wlk-seed-lot-1",
        "--confirm",
    ], env)
    seed_lot_id = fields["PUBLIC_ID"]

    header(f"Commissioning SEMINA da {seed_lot_id} (tpo semina commission)")
    semina_provenance = json.dumps({
        "physical_started_at": "OWNER_AUTHORIZED", "actual_seed_grams": "OWNER_AUTHORIZED",
        "selected_lse": "OWNER_AUTHORIZED", "selected_pv": "OWNER_AUTHORIZED",
        "origin": "OWNER_AUTHORIZED",
    })
    fields, _ = run_cli([
        "semina", "commission",
        "--seed-lot", seed_lot_id, "--expected-seed-lot-version", "0",
        "--protocol-version", PV_ID, "--actual-seed-grams", "5",
        "--physical-started-at", BASE.isoformat(), "--origin", "ORDINE_CLIENTE",
        "--provenance", semina_provenance,
        "--actor", "walkthrough", "--reason", "Walkthrough end-to-end",
        "--correlation-id", "wlk-semina", "--idempotency-key", "wlk-semina-1",
        "--confirm",
    ], env)
    semina_id = fields["PUBLIC_ID"]

    transition_provenance = json.dumps({"target_state": "OWNER_AUTHORIZED", "effective_at": "OWNER_AUTHORIZED"})
    lifecycle = (
        ("GERMINAZIONE", 0, BASE + timedelta(days=1)),
        ("LUCE", 1, BASE + timedelta(days=2)),
        ("CRESCITA", 2, BASE + timedelta(days=3)),
        ("PRONTA_ALLA_RACCOLTA", 3, BASE + timedelta(days=10)),
    )
    for target_state, expected_version, effective_at in lifecycle:
        header(f"Transizione SEMINA {semina_id} -> {target_state} (tpo semina transition)")
        run_cli([
            "semina", "transition",
            "--semina", semina_id, "--expected-semina-version", str(expected_version),
            "--target-state", target_state, "--effective-at", effective_at.isoformat(),
            "--provenance", transition_provenance,
            "--actor", "walkthrough", "--reason", "Walkthrough end-to-end",
            "--correlation-id", f"wlk-transition-{expected_version}",
            "--idempotency-key", f"wlk-transition-{expected_version}",
            "--confirm",
        ], env)

    header(f"Registrazione RACCOLTA da {semina_id} (tpo raccolta record)")
    fields, _ = run_cli([
        "raccolta", "record",
        "--semina", semina_id, "--quantity", "5", "--uom", "SET",
        "--effective-at", (BASE + timedelta(days=11)).isoformat(),
        "--actor", "walkthrough", "--reason", "Walkthrough end-to-end",
        "--correlation-id", "wlk-raccolta", "--idempotency-key", "wlk-raccolta-1",
        "--confirm",
    ], env)
    raccolta_id = fields["RACCOLTA_ID"]

    header(f"Carico a magazzino da {raccolta_id} (tpo movimento carica-raccolta)")
    fields, _ = run_cli([
        "movimento", "carica-raccolta",
        "--raccolta", raccolta_id, "--quantita-pesata", "1200",
        "--effective-at", (BASE + timedelta(days=11, hours=2)).isoformat(),
        "--motivo", "Carico da raccolta walkthrough",
        "--actor", "walkthrough", "--reason", "Walkthrough end-to-end",
        "--correlation-id", "wlk-movimento", "--idempotency-key", "wlk-movimento-1",
        "--confirm",
    ], env)
    note(f"STOCK_DISPONIBILE dopo il carico: {fields.get('STOCK_DISPONIBILE')} GRAM")

    header(f"Consegna dell'intera riga {RO_ID} (tpo delivery fulfil)")
    lines_fd, lines_path = tempfile.mkstemp(prefix="wlk-delivery-", suffix=".json")
    os.close(lines_fd)
    lines_file = Path(lines_path)
    lines_file.write_text(json.dumps([{
        "order_id": ORD_ID, "order_line_id": RO_ID, "quantity": RIGA_QUANTITA,
        "unit": RIGA_UOM, "expected_order_version": 0, "expected_order_line_version": 0,
    }]))
    try:
        fields, _ = run_cli([
            "delivery", "fulfil",
            "--client", CLI_ID, "--planned-date", (BASE + timedelta(days=13)).date().isoformat(),
            "--effective-at", (BASE + timedelta(days=13)).isoformat(),
            "--lines-file", str(lines_file),
            "--actor", "walkthrough", "--reason", "Walkthrough end-to-end",
            "--correlation-id", "wlk-delivery",
            "--confirm",
        ], env)
    finally:
        lines_file.unlink(missing_ok=True)
    consegna_id = fields["CONSEGNA_ID"]

    header(f"Assegnazione fisica {raccolta_id} <-> {RO_ID} (tpo assegnazione registra)")
    run_cli([
        "assegnazione", "registra",
        "--raccolta", raccolta_id, "--riga-ordine", RO_ID, "--consegna", consegna_id,
        "--quantita", RIGA_QUANTITA, "--unita-misura", RIGA_UOM,
        "--effective-at", (BASE + timedelta(days=13, hours=1)).isoformat(),
        "--motivo", "Assegnazione fisica walkthrough",
        "--actor", "walkthrough", "--reason", "Walkthrough end-to-end",
        "--correlation-id", "wlk-assegnazione", "--idempotency-key", "wlk-assegnazione-1",
        "--confirm",
    ], env)

    header(f"Emissione FATTURA per {consegna_id} (tpo fattura emetti)")
    fields, _ = run_cli([
        "fattura", "emetti",
        "--client", CLI_ID, "--consegna", consegna_id,
        "--data-emissione", (BASE + timedelta(days=14)).date().isoformat(),
        "--actor", "walkthrough", "--reason", "Walkthrough end-to-end",
        "--correlation-id", "wlk-fattura", "--idempotency-key", "wlk-fattura-1",
        "--confirm",
    ], env)
    numero_fattura = fields["NUMERO_FATTURA"]
    totale = fields["TOTALE"]

    header(f"Registrazione INCASSO per {numero_fattura} (tpo incasso registra)")
    run_cli([
        "incasso", "registra",
        "--fattura", numero_fattura, "--importo", totale,
        "--data", (BASE + timedelta(days=20)).date().isoformat(), "--metodo", "BONIFICO",
        "--actor", "walkthrough", "--reason", "Walkthrough end-to-end",
        "--correlation-id", "wlk-incasso", "--idempotency-key", "wlk-incasso-1",
    ], env)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep", action="store_true",
        help="Non fermare/distruggere il cluster disponibile a fine esecuzione.",
    )
    args = parser.parse_args()

    if not VENV_PYTHON.exists():
        log(f"Non trovo l'interprete del virtualenv in {VENV_PYTHON}.")
        log("Esegui prima `./bootstrap.sh` nella radice del repository.")
        return 1

    root = Path(tempfile.mkdtemp(prefix="tpo-walkthrough-"))
    cluster = None
    engine = None
    exit_code = 0
    try:
        header("Avvio di un cluster PostgreSQL locale, disponibile e isolato")
        cluster = start_cluster(root)
        dbname = "tpo_walkthrough"
        env = cli_environment(cluster, dbname)

        header("Migrazione dello schema a head (alembic upgrade head)")
        engine = create_database_and_migrate(cluster, dbname)
        log(f"Database '{dbname}' creato e migrato a head.")

        run_chain(env, engine)

        header("Traccia end-to-end (una sola query, dal CLIENTE all'INCASSO)")
        rows = final_trace(engine, cliente_public_id=CLI_ID)
        for row in rows:
            for key, value in row.items():
                log(f"  {key}: {value}")

        header("Verifica DISPONIBILITA_COMMERCIALE (PRENOTATO/VENDIBILE, servizio a sola lettura)")
        disponibilita = check_disponibilita_commerciale(env, varieta_public_id=VAR_ID)
        log(f"  varieta_id: {disponibilita.varieta_id.value}")
        log(f"  disponibile: {disponibilita.disponibile} {disponibilita.unita_misura}")
        log(f"  prenotato:   {disponibilita.prenotato} {disponibilita.unita_misura}")
        log(f"  vendibile:   {disponibilita.vendibile} {disponibilita.unita_misura}")
        log(f"  integrita_allarme: {disponibilita.integrita_allarme}")

        log()
        log("WALKTHROUGH COMPLETATO: l'intera catena e' collegata end-to-end ed e' coerente.")
    except WalkthroughError as exc:
        log()
        log(f"WALKTHROUGH INTERROTTO: {exc}")
        if cluster is not None:
            log(
                "Il cluster disponibile e' rimasto attivo per ispezione manuale: "
                f"psql 'postgresql://postgres@127.0.0.1:{cluster['port']}/tpo_walkthrough?sslmode=require' "
                f"(data dir: {cluster['data']})."
            )
            log(f"Per fermarlo: {cluster['pg_ctl']} -D {cluster['data']} -m fast stop")
        exit_code = 1
    finally:
        if engine is not None:
            engine.dispose()

    if cluster is not None and exit_code == 0:
        if args.keep:
            log()
            log("Cluster lasciato attivo su richiesta (--keep):")
            log(f"  psql 'postgresql://postgres@127.0.0.1:{cluster['port']}/tpo_walkthrough?sslmode=require'")
            log(f"  Per fermarlo: {cluster['pg_ctl']} -D {cluster['data']} -m fast stop")
        else:
            stop_cluster(cluster)
            shutil.rmtree(root, ignore_errors=True)
            log()
            log("Cluster disponibile fermato e rimosso: nessuna traccia lasciata sul disco.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
