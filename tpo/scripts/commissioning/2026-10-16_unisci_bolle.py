"""UNISCE due o piu' bolle dello stesso cliente in una sola (16/10/2026, richiesta di Matteo: le due bolle di Puipana).

Non tocca il database (legge soltanto) e NON cambia nessuna consegna: le righe restano quelle delle singole CONSEGNE,
ognuna con scritto da quale consegna e da quale giorno viene. Il PDF unico va in ~/Desktop/bolle/<cliente>/ con il nome
  bolla_CON-000020_CON-000024_puipana_2026-10-16.pdf
e con --esegui i PDF singoli di quelle consegne vengono SPOSTATI (non cancellati) in ~/Desktop/bolle/<cliente>/unite/.
Si rifiuta, senza scrivere nulla, se le consegne sono di clienti diversi, non sono CONSEGNATE, o se alcune sono pagate e
altre no (o con data/metodo diversi). Rilanciabile: se la bolla unica esiste gia' la salta; con --sovrascrivi la rifa (anche i PDF singoli in unite/ vengono rimpiazzati).

Uso (dalla cartella del progetto):
  .venv/bin/python scripts/commissioning/2026-10-16_unisci_bolle.py CON-000020 CON-000024            # anteprima
  .venv/bin/python scripts/commissioning/2026-10-16_unisci_bolle.py CON-000020 CON-000024 --esegui
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))

LOCAL_TZ = ZoneInfo("Atlantic/Canary")
DEFAULT_CARTELLA = Path.home() / "Desktop" / "bolle"


def _n(value) -> str:
    text = format(value.normalize(), "f")
    return (text.rstrip("0").rstrip(".") if "." in text else text).replace(".", ",") or "0"


def run(service, codici: list[str], cartella: Path, esegui: bool, emittente=(), out=print, sovrascrivi: bool = False,
        ora: datetime | None = None) -> int:
    from src.tpo_core.application.bolla_lettura import BollaLetturaError, RichiediBolla, unisci_bolle
    from src.tpo_core.cli.bolla import _slug
    from src.tpo_core.domain.errors import InvalidIdentifierError
    from src.tpo_core.domain.identifiers import ConsegnaId
    from src.tpo_core.infrastructure.pdf.bolla_pdf import estado_pagamento, render_bolla_pdf

    out(f"== UNISCI BOLLE {' + '.join(codici)} ({'ESECUZIONE' if esegui else 'ANTEPRIMA, NULLA VIENE SCRITTO'})")
    try:
        bolle = [service.bolla(RichiediBolla(ConsegnaId(c))) for c in codici]
        unita = unisci_bolle(bolle)
    except (BollaLetturaError, InvalidIdentifierError) as exc:
        out(f"RIFIUTATO, nulla scritto: {exc}")
        return 2
    cliente = _slug(unita.cliente_denominazione)
    cartella_cliente = cartella / cliente
    giorno = (unita.data_effettiva.astimezone(LOCAL_TZ).date() if unita.data_effettiva else unita.data_prevista)
    nome = f"bolla_{'_'.join(unita.consegne_unite)}_{cliente}_{giorno.isoformat()}.pdf"
    destinazione = cartella_cliente / nome

    out(f"Cliente: {unita.cliente_denominazione} ({unita.cliente_id}); pagamento: {estado_pagamento(unita)}")
    for riga in unita.righe:
        out(f"  {riga.posizione}. {riga.varieta_denominazione}  {_n(riga.quantita)} {riga.unita_misura.lower()}"
            f"   [{riga.consegna_origine} del {riga.data_consegna_origine:%d/%m/%Y}]")
    out(f"File: {destinazione}")
    if destinazione.exists() and not sovrascrivi:
        out("La bolla unica esiste gia': non la rifaccio (nessun file toccato). Per rifarla, ad esempio dopo un pagamento: --sovrascrivi.")
        return 0

    pdf = render_bolla_pdf(unita, emittente=emittente, generata_il=ora or datetime.now(LOCAL_TZ))
    singoli = [p for c in unita.consegne_unite for p in sorted(cartella_cliente.glob(f"bolla_{c}_*.pdf")) if p != destinazione]
    for p in singoli:
        out(f"  {'sposto' if esegui else 'sposterei'} in unite/: {p.name}")
    if not esegui:
        out("ANTEPRIMA: nulla e' stato scritto. Per eseguire aggiungi --esegui")
        return 0
    cartella_cliente.mkdir(parents=True, exist_ok=True)
    with open(destinazione, "wb" if sovrascrivi else "xb") as handle:
        handle.write(pdf)
    if singoli:
        (cartella_cliente / "unite").mkdir(exist_ok=True)
    for p in singoli:
        dest = cartella_cliente / "unite" / p.name
        if dest.exists() and not sovrascrivi:
            out(f"  SALTO {p.name}: esiste gia' in unite/ (non sovrascrivo)")
            continue
        shutil.move(str(p), str(dest))
    out(f"FATTO: {destinazione}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("consegne", nargs="+", metavar="CON-000000", help="almeno due consegne dello stesso cliente")
    ap.add_argument("--cartella", default=str(DEFAULT_CARTELLA))
    ap.add_argument("--esegui", action="store_true", help="scrive davvero (senza: solo anteprima)")
    ap.add_argument("--sovrascrivi", action="store_true", help="rifa la bolla unica se esiste gia' (es. dopo un pagamento)")
    a = ap.parse_args()
    if len(a.consegne) < 2:
        print("Servono almeno due consegne.")
        return 2
    from secret_boundary import load_postgresql_parameters
    from src.tpo_core.bootstrap import build_bolla_lettura_service
    from src.tpo_core.cli.bolla import DEFAULT_EMITTENTE_FILE, _load_emittente
    from src.tpo_core.infrastructure.postgresql.settings import PostgreSQLSettings
    p = load_postgresql_parameters()
    settings = PostgreSQLSettings.from_mapping({
        "host": p["host"], "port": p["port"], "database": p["dbname"], "user": p["user"],
        "password": p["password"], "sslmode": p["sslmode"], "connect_timeout_seconds": p["connect_timeout"]})
    service = build_bolla_lettura_service(settings)
    return run(service, a.consegne, Path(a.cartella).expanduser(), a.esegui, sovrascrivi=a.sovrascrivi,
               emittente=_load_emittente(DEFAULT_EMITTENTE_FILE, required=False))


if __name__ == "__main__":
    sys.exit(main())
