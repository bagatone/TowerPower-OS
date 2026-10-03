"""Thin CLI adapter per la BOLLA DI CONSEGNA V1 (sola lettura dal database).

``tpo bolla genera --consegna CON-000012`` legge la CONSEGNA, le sue righe e
la provenienza di lotto registrata (tpo.consumi_lotto) e salva un PDF in una
cartella locale. Non scrive nulla sul database e non richiede --confirm.
Autorita': docs/architecture/CONSUMO_LOTTO_AUTHORITY_FREEZE.md.

Intestazione emittente: righe di testo lette da config/bolla_emittente.yaml
(chiave ``righe``), se esiste; altrimenti il PDF riporta solo "Tower Power".
Nessun dato anagrafico viene inventato.
"""

from __future__ import annotations

import re
import unicodedata
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from typing import TextIO
from zoneinfo import ZoneInfo

from ..application.bolla_lettura.errors import BollaLetturaError, InvalidBollaLetturaQueryError
from ..application.bolla_lettura.models import RichiediBolla
from ..bootstrap import build_bolla_lettura_service
from ..domain.errors import InvalidIdentifierError
from ..domain.identifiers import ConsegnaId
from ..infrastructure.postgresql.errors import PostgreSQLError
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .exit_codes import OperationalExitCode

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "bolle"
DEFAULT_EMITTENTE_FILE = ROOT / "config" / "bolla_emittente.yaml"
LOCAL_TZ = ZoneInfo("Atlantic/Canary")


def run_bolla_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.bolla_command != "genera":
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    try:
        consegna_id = ConsegnaId(args.consegna)
        emittente = _load_emittente(
            Path(args.emittente_file) if args.emittente_file else DEFAULT_EMITTENTE_FILE,
            required=bool(args.emittente_file),
        )
        try:
            # Import pigro: reportlab serve solo a questo comando, cosi' un
            # ambiente senza reportlab non rompe gli altri comandi `tpo`.
            from ..infrastructure.pdf.bolla_pdf import render_bolla_pdf
        except ImportError:
            print(
                "BOLLA_FAILED: BOLLA_DIPENDENZA_MANCANTE: reportlab non installato "
                "(.venv/bin/python -m pip install -r requirements.txt).", file=stderr,
            )
            return OperationalExitCode.OPERATION_RUNTIME_UNAVAILABLE
        service = build_bolla_lettura_service(PostgreSQLSettings.from_environment())
        bolla = service.bolla(RichiediBolla(consegna_id))
        pdf = render_bolla_pdf(
            bolla, emittente=emittente, generata_il=datetime.now(LOCAL_TZ),
        )
        output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        data = (bolla.data_effettiva.astimezone(LOCAL_TZ).date()
                if bolla.data_effettiva else bolla.data_prevista)
        path = output_dir / (
            f"bolla_{bolla.consegna_id.value}_{_slug(bolla.cliente_denominazione)}"
            f"_{data.isoformat()}.pdf"
        )
        try:
            with open(path, "wb" if args.sovrascrivi else "xb") as handle:
                handle.write(pdf)
        except FileExistsError:
            print(
                f"BOLLA_FAILED: BOLLA_FILE_ESISTENTE: {path.name} esiste gia' in "
                f"{output_dir}; usare --sovrascrivi per rigenerarla.", file=stderr,
            )
            return OperationalExitCode.OPERATION_FAILED
    except (ValueError, TypeError, InvalidIdentifierError, InvalidBollaLetturaQueryError) as exc:
        print(f"BOLLA_FAILED: BOLLA_INPUT_INVALID: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_INPUT_INVALID
    except BollaLetturaError as exc:
        print(f"BOLLA_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_FAILED
    except PostgreSQLError as exc:
        print(f"BOLLA_FAILED: DATABASE: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RUNTIME_UNAVAILABLE
    except OSError as exc:
        print(f"BOLLA_FAILED: BOLLA_FILE_NON_SCRIVIBILE: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_FAILED
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR

    print("STATUS: GENERATED", file=stdout)
    print("ENTITY: BOLLA", file=stdout)
    print(f"CONSEGNA: {bolla.consegna_id.value}", file=stdout)
    print(f"CLIENTE: {bolla.cliente_id}", file=stdout)
    print(f"RIGHE: {len(bolla.righe)}", file=stdout)
    print(f"RIGHE_CON_QUANTITA_SENZA_ORIGINE: {bolla.righe_senza_origine}", file=stdout)
    print(f"FILE: {path}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED


def _slug(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").lower()
    return slug or "cliente"


def _load_emittente(path: Path, *, required: bool) -> tuple[str, ...]:
    if not path.is_file():
        if required:
            raise ValueError(f"--emittente-file non trovato: {path}")
        return ()
    import yaml

    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    righe = loaded.get("righe") if isinstance(loaded, dict) else None
    if not isinstance(righe, list) or not all(isinstance(item, str) for item in righe):
        raise ValueError(f"{path.name}: attesa una chiave 'righe' con una lista di testi.")
    return tuple(righe)
