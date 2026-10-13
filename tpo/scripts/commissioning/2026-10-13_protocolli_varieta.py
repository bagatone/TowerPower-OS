"""Sola lettura: elenca le versioni di protocollo di una varieta' con la loro validita' (valida_dal / valida_al).

Serve quando una semina passata viene rifiutata con PROTOCOL_NOT_FOUND_OR_UNAVAILABLE: il sistema accetta solo una
versione di protocollo APPROVATA e valida nel giorno di semina dichiarato.

Uso:  .venv/bin/python scripts/commissioning/2026-10-13_protocolli_varieta.py Rucola
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location(
    "commission_base", ROOT / "scripts" / "commissioning" / "2026-10-04_commission_semine_afila_cilantro.py")
base = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = base
_spec.loader.exec_module(base)


def main() -> int:
    nome = sys.argv[1] if len(sys.argv) > 1 else "Rucola"
    conn = base.db()
    cur = conn.cursor()
    cur.execute("""SELECT pv.public_id, pv.stato_approvazione::text, pv.valida_dal, pv.valida_al,
                          pv.grammi_seme_per_set, pv.germinazione_giorni, pv.crescita_luce_giorni, p.tipo::text, up.codice
                   FROM tpo.protocollo_versioni pv
                   JOIN tpo.protocolli p ON p.id=pv.protocollo_id
                   JOIN tpo.cultivar_usi cu ON cu.id=p.cultivar_uso_id
                   JOIN tpo.cultivar c ON c.id=cu.cultivar_id
                   JOIN tpo.varieta v ON v.id=c.varieta_id
                   JOIN tpo.usi_produttivi up ON up.id=cu.uso_produttivo_id
                   WHERE v.denominazione=%s ORDER BY pv.valida_dal, pv.id""", (nome,))
    rows = cur.fetchall()
    print(f"== PROTOCOLLI di {nome} (sola lettura)")
    if not rows:
        print("  nessuna versione trovata")
    for pv, stato, dal, al, grammi, germ, luce, tipo, uso in rows:
        print(f"  {pv}: {stato}, valida dal {dal} al {al or 'oggi (corrente)'}, {grammi} g/SET, germinazione {germ} gg, "
              f"luce {luce} gg, {tipo}/{uso}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
