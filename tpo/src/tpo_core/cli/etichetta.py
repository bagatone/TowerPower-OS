"""Thin CLI adapter per le ETICHETTE DI TRACCIABILITA' (sola lettura dal database).

``tpo etichetta genera --consegna CON-000004`` legge la stessa vista della BOLLA
(consegna, righe, provenienza di lotto) e salva un PDF con UNA etichetta
(62x29 mm) per SET (--etichette-per-set, default 1; una frazione di SET, es. 0.5,
riceve comunque 1 etichetta per origine di lotto). Non scrive
nulla sul database e non richiede --confirm. Le quantita' senza origine
tracciata NON ricevono etichetta (nessun codice inventato): vengono segnalate.
"""
from __future__ import annotations

from argparse import Namespace
from decimal import ROUND_CEILING, Decimal
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
from .bolla import _slug
from .exit_codes import OperationalExitCode

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "etichette"
LOCAL_TZ = ZoneInfo("Atlantic/Canary")


class _EtichetteError(Exception):
    pass


def costruisci_etichette(bolla, etichette_per_set: int = 1):
    from ..infrastructure.pdf.etichette_pdf import Etichetta

    etichette, senza_origine = [], []
    for riga in bolla.righe:
        if riga.unita_misura != "SET":
            raise _EtichetteError(
                f"{riga.varieta_denominazione}: unita' {riga.unita_misura}, le etichette "
                "sono definite solo per SET.")
        if riga.quantita_senza_origine > 0:
            senza_origine.append(f"{riga.varieta_denominazione} {riga.quantita_senza_origine} SET")
        for origine in riga.origini:
            if origine.quantita <= 0:
                raise _EtichetteError(
                    f"{riga.varieta_denominazione} {origine.codice_tracciabilita}: quantita' {origine.quantita} non valida.")
            n = int((origine.quantita * etichette_per_set).to_integral_value(rounding=ROUND_CEILING))
            data = origine.data_raccolta
            data = data.astimezone(LOCAL_TZ).date() if data.tzinfo is not None else data.date()
            etichette.extend(
                [Etichetta(riga.varieta_denominazione, origine.codice_tracciabilita, data, bolla.consegna_id.value)]
                * n
            )
    return etichette, senza_origine


def run_etichetta_command(args: Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    if args.etichetta_command != "genera":
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR
    try:
        consegna_id = ConsegnaId(args.consegna)
        if args.etichette_per_set < 1:
            raise ValueError("--etichette-per-set deve essere >= 1.")
        try:
            from ..infrastructure.pdf.etichette_pdf import render_etichette_pdf
        except ImportError:
            print("ETICHETTA_FAILED: DIPENDENZA_MANCANTE: reportlab non installato "
                  "(.venv/bin/python -m pip install -r requirements.txt).", file=stderr)
            return OperationalExitCode.OPERATION_RUNTIME_UNAVAILABLE
        service = build_bolla_lettura_service(PostgreSQLSettings.from_environment())
        bolla = service.bolla(RichiediBolla(consegna_id))
        etichette, senza_origine = costruisci_etichette(bolla, args.etichette_per_set)
        if not etichette:
            raise _EtichetteError("nessuna etichetta: la consegna non ha quantita' con origine tracciata.")
        pdf = render_etichette_pdf(etichette)
        output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        data = (bolla.data_effettiva.astimezone(LOCAL_TZ).date()
                if bolla.data_effettiva else bolla.data_prevista)
        path = output_dir / (f"etichette_{bolla.consegna_id.value}_{_slug(bolla.cliente_denominazione)}"
                             f"_{data.isoformat()}.pdf")
        try:
            with open(path, "wb" if args.sovrascrivi else "xb") as handle:
                handle.write(pdf)
        except FileExistsError:
            print(f"ETICHETTA_FAILED: FILE_ESISTENTE: {path.name} esiste gia' in {output_dir}; "
                  "usare --sovrascrivi per rigenerarlo.", file=stderr)
            return OperationalExitCode.OPERATION_FAILED
    except (ValueError, TypeError, InvalidIdentifierError, InvalidBollaLetturaQueryError, _EtichetteError) as exc:
        print(f"ETICHETTA_FAILED: INPUT_INVALID: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_INPUT_INVALID
    except BollaLetturaError as exc:
        print(f"ETICHETTA_FAILED: {exc.code}: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_FAILED
    except PostgreSQLError as exc:
        print(f"ETICHETTA_FAILED: DATABASE: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_RUNTIME_UNAVAILABLE
    except OSError as exc:
        print(f"ETICHETTA_FAILED: FILE_NON_SCRIVIBILE: {exc}", file=stderr)
        return OperationalExitCode.OPERATION_FAILED
    except Exception:
        print("OPERATION_INTERNAL_ERROR", file=stderr)
        return OperationalExitCode.OPERATION_INTERNAL_ERROR

    print("STATUS: GENERATED", file=stdout)
    print("ENTITY: ETICHETTE", file=stdout)
    print(f"CONSEGNA: {bolla.consegna_id.value}", file=stdout)
    print(f"CLIENTE: {bolla.cliente_id}", file=stdout)
    print(f"ETICHETTE: {len(etichette)}", file=stdout)
    conteggio: dict[str, int] = {}
    for e in etichette:
        chiave = f"{e.varieta} {e.codice_tracciabilita}"
        conteggio[chiave] = conteggio.get(chiave, 0) + 1
    for chiave, n in conteggio.items():
        print(f"  {chiave}: {n}", file=stdout)
    if senza_origine:
        print("ATTENZIONE_SENZA_ORIGINE: " + "; ".join(senza_origine) + " (nessuna etichetta emessa)", file=stdout)
    print(f"FILE: {path}", file=stdout)
    return OperationalExitCode.OPERATION_COMMITTED
