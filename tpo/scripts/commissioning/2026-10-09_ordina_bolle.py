"""Mette in ordine le bolle PDF gia' salvate: una sottocartella per cliente (9/10/2026, richiesta di Matteo).

Le bolle nuove vengono gia' salvate cosi' (`tpo bolla genera --per-cliente`). Questo script sposta quelle vecchie,
che stanno tutte insieme nella cartella, nella sottocartella del loro cliente:
  ~/Desktop/bolle/bolla_CON-000008_splash_2026-10-09.pdf  ->  ~/Desktop/bolle/splash/bolla_CON-000008_splash_2026-10-09.pdf

Il cliente si legge dal nome del file (come l'ha scritto il sistema). Senza --esegui NON sposta nulla (anteprima).
Non cancella e non sovrascrive mai: se nella sottocartella esiste gia' un file con lo stesso nome lo salta e lo dice;
i file che non sono bolle (nome diverso) restano dove sono. Rilanciabile.

Uso:
  .venv/bin/python scripts/commissioning/2026-10-09_ordina_bolle.py                  # anteprima
  .venv/bin/python scripts/commissioning/2026-10-09_ordina_bolle.py --esegui
  ... --cartella /altra/cartella
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

DEFAULT = Path.home() / "Desktop" / "bolle"
PATTERN = re.compile(r"^bolla_(CON-\d{6,})_(?P<cliente>[a-z0-9]+(?:-[a-z0-9]+)*)_(\d{4}-\d{2}-\d{2})\.pdf$")


def run(folder: Path, esegui: bool, out=print) -> int:
    if not folder.is_dir():
        out(f"RIFIUTATO, nulla spostato: {folder} non e' una cartella.")
        return 2
    out(f"== ORDINA BOLLE in {folder} ({'ESECUZIONE' if esegui else 'ANTEPRIMA, NULLA VIENE SPOSTATO'})")
    moved = skipped = other = 0
    for path in sorted(p for p in folder.iterdir() if p.is_file()):
        match = PATTERN.match(path.name)
        if not match:
            if path.suffix.lower() == ".pdf":
                out(f"  lascio dov'e': {path.name} (non e' nel formato bolla_CON-..._cliente_data.pdf)")
            other += 1
            continue
        dest_dir = folder / match["cliente"]
        dest = dest_dir / path.name
        if dest.exists():
            out(f"  SALTO {path.name}: esiste gia' in {match['cliente']}/ (non sovrascrivo)")
            skipped += 1
            continue
        out(f"  {path.name} -> {match['cliente']}/")
        if esegui:
            dest_dir.mkdir(exist_ok=True)
            shutil.move(str(path), str(dest))
        moved += 1
    out(f"\n{'Spostate' if esegui else 'Da spostare'}: {moved}; saltate: {skipped}; altri file lasciati: {other}")
    if not esegui:
        out("ANTEPRIMA: nulla e' stato spostato. Per eseguire aggiungi --esegui")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cartella", default=str(DEFAULT))
    ap.add_argument("--esegui", action="store_true", help="sposta davvero (senza: solo anteprima)")
    a = ap.parse_args()
    return run(Path(a.cartella).expanduser(), a.esegui)


if __name__ == "__main__":
    sys.exit(main())
