"""Revisione governata di un PROTOCOLLO agronomico: nuova versione N+1 al posto della corrente.

Addendum 7/10/2026 (Owner: Matteo: "procediamo con la formulazione del nuovo comando"). Chiude il gap noto dal
19/9/2026 (``tpo protocollo commission`` accetta solo ``version == 1``): ``2026-09-19_revisiona_protocollo_hinojo``
fu l'unico precedente, una transazione scritta a mano. Qui lo stesso schema diventa una autorita' riusabile.

In una sola transazione, per la versione APPROVATA corrente (``valida_al IS NULL``) di UNA varieta' MICROGREEN:
1. la versione corrente viene CHIUSA (``valida_al = valida_dal della nuova``): e' l'UNICA modifica ammessa su una
   versione esistente (il vincolo EXCLUDE sulla validita' impedisce range sovrapposti);
2. nasce la versione N+1, APPROVATA, collegata alla precedente (``versione_precedente_id``), con TUTTI i campi copiati
   dalla corrente tranne quelli dichiarati; motivo ed eventuale evidenza obbligatori;
3. due eventi ``audit_eventi``: UPDATE sulla vecchia (chiusura), INSERT sulla nuova con le variazioni (da -> a).

Non e' retroattiva: ``valida_dal`` non puo' essere anteriore a oggi (ne' alla validita' della versione corrente).
Le SEMINE gia' avviate tengono ``protocollo_versione_id`` della versione con cui sono partite; le loro finestre
predittive gia' compilate non cambiano (il comando predittivo non sovrascrive). Il planner e il commissioning delle
semine usano la versione valida alla data di riferimento.

Rifiuta: varieta' inesistente o senza esattamente UNA versione corrente APPROVATA; nessuna variazione o valori
identici alla corrente; durate negative, lead min > max, grammi/resa/granularita' <= 0; validita' non successiva.

Usa un cursore DB-API (psycopg, ``%s``); non fa commit.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


class ProtocolRevisionError(ValueError):
    """Pre-condizione non soddisfatta: nulla e' stato scritto."""


COLUMNS = (
    "id,protocollo_id,numero_versione,valida_dal,valida_al,contenuto,motivazione,evidenze,public_id,"
    "stato_approvazione,idratazione_ore,orario_semina_previsto,orario_raccolta_target,germinazione_giorni,"
    "crescita_luce_giorni,grammi_seme_per_set,resa_attesa,resa_unita_misura,granularita_produttiva,"
    "harvest_min_lead_giorni,harvest_max_lead_giorni,buffer_temporale_minuti"
)

# nome parametro -> (colonna, tipo)
FIELDS: dict[str, tuple[str, str]] = {
    "hydration_hours": ("idratazione_ore", "decimal"),
    "germination_days": ("germinazione_giorni", "int"),
    "light_growth_days": ("crescita_luce_giorni", "int"),
    "seed_grams_per_set": ("grammi_seme_per_set", "decimal"),
    "expected_yield": ("resa_attesa", "decimal"),
    "production_granularity": ("granularita_produttiva", "decimal"),
    "harvest_min_lead_days": ("harvest_min_lead_giorni", "int"),
    "harvest_max_lead_days": ("harvest_max_lead_giorni", "int"),
    "temporal_buffer_minutes": ("buffer_temporale_minuti", "int"),
    "planned_sowing_time": ("orario_semina_previsto", "time"),
    "target_harvest_time": ("orario_raccolta_target", "time"),
}


@dataclass(frozen=True)
class Revision:
    variety: str
    old: dict[str, Any]
    new_values: dict[str, Any]          # colonna -> nuovo valore (solo quelle cambiate)
    changes: dict[str, tuple[Any, Any]]  # parametro -> (da, a)
    new_public_id: str
    valid_from: date
    open_semine: tuple[tuple[str, str], ...]   # (SEM, stato) ancora legate alla versione corrente


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn").strip()


def _norm(kind: str, value: Any) -> Any:
    try:
        if kind == "int":
            if isinstance(value, bool) or int(value) != value:
                raise ValueError
            return int(value)
        if kind == "decimal":
            if isinstance(value, float):
                raise ValueError
            return Decimal(str(value))
        if kind == "time":
            return value if isinstance(value, time) else time.fromisoformat(str(value))
    except (ValueError, TypeError, InvalidOperation):
        raise ProtocolRevisionError(f"valore non valido: {value!r}")
    raise ProtocolRevisionError(f"tipo sconosciuto {kind}")


def _same(kind: str, a: Any, b: Any) -> bool:
    if kind == "decimal":
        return Decimal(a) == Decimal(b)
    return a == b


def current_version(cursor: Any, variety: str, *, lock: bool = False) -> dict[str, Any]:
    cursor.execute(
        f"""SELECT v.denominazione,{', '.join('pv.' + c for c in COLUMNS.split(','))}
            FROM tpo.protocollo_versioni pv
            JOIN tpo.protocolli p ON p.id=pv.protocollo_id
            JOIN tpo.cultivar_usi cu ON cu.id=p.cultivar_uso_id
            JOIN tpo.cultivar c ON c.id=cu.cultivar_id
            JOIN tpo.varieta v ON v.id=c.varieta_id
            JOIN tpo.usi_produttivi up ON up.id=cu.uso_produttivo_id AND up.codice='MICROGREEN'
            WHERE pv.stato_approvazione='APPROVATA' AND pv.valida_al IS NULL
            ORDER BY v.denominazione, pv.id {'FOR UPDATE OF pv' if lock else ''}""")
    rows = [r for r in cursor.fetchall() if _fold(r[0]) == _fold(variety)]
    if len(rows) != 1:
        raise ProtocolRevisionError(
            f"{variety}: trovate {len(rows)} versioni di protocollo APPROVATE correnti (attesa 1).")
    data = dict(zip(["variety"] + COLUMNS.split(","), rows[0]))
    return data


def _validate(old: dict[str, Any], new: dict[str, Any]) -> None:
    for column in ("germinazione_giorni", "crescita_luce_giorni", "harvest_min_lead_giorni",
                   "harvest_max_lead_giorni", "buffer_temporale_minuti"):
        if new[column] < 0:
            raise ProtocolRevisionError(f"{column} non puo' essere negativo.")
    if Decimal(new["idratazione_ore"]) < 0:
        raise ProtocolRevisionError("idratazione_ore non puo' essere negativa.")
    for column in ("grammi_seme_per_set", "resa_attesa", "granularita_produttiva"):
        if Decimal(new[column]) <= 0:
            raise ProtocolRevisionError(f"{column} deve essere maggiore di 0.")
    if new["harvest_min_lead_giorni"] > new["harvest_max_lead_giorni"]:
        raise ProtocolRevisionError("harvest_min_lead_days non puo' superare harvest_max_lead_days.")


def prepare(cursor: Any, variety: str, changes: dict[str, Any], valid_from: date, today: date,
            *, lock: bool = False) -> Revision:
    unknown = sorted(set(changes) - set(FIELDS))
    if unknown:
        raise ProtocolRevisionError(f"parametri non revisionabili: {', '.join(unknown)}")
    old = current_version(cursor, variety, lock=lock)
    diff: dict[str, tuple[Any, Any]] = {}
    new_values: dict[str, Any] = {}
    for name, raw in changes.items():
        if raw is None:
            continue
        column, kind = FIELDS[name]
        value = _norm(kind, raw)
        if not _same(kind, old[column], value):
            diff[name] = (old[column], value)
            new_values[column] = value
    if not diff:
        raise ProtocolRevisionError(
            f"Nessuna differenza: {old['public_id']} ha gia' questi valori (nessuna nuova versione).")
    merged = {**old, **new_values}
    _validate(old, merged)
    if valid_from < today:
        raise ProtocolRevisionError(
            f"valida dal {valid_from} e' nel passato (oggi {today}): una revisione non e' retroattiva.")
    if valid_from <= old["valida_dal"]:
        raise ProtocolRevisionError(
            f"valida dal {valid_from} non successiva alla validita' attuale ({old['public_id']} dal {old['valida_dal']}).")
    cursor.execute("SELECT public_id FROM tpo.protocollo_versioni WHERE public_id ~ '^PV-[0-9]{6,}$'")
    numbers = [int(re.match(r"^PV-(\d+)$", r[0]).group(1)) for r in cursor.fetchall()]
    new_public_id = f"PV-{(max(numbers) if numbers else 0) + 1:06d}"
    cursor.execute(
        """SELECT public_id,stato::text FROM tpo.semine WHERE protocollo_versione_id=%s AND stato<>'CHIUSA'
           ORDER BY id""", (old["id"],))
    open_semine = tuple((r[0], r[1]) for r in cursor.fetchall())
    return Revision(old["variety"], old, new_values, diff, new_public_id, valid_from, open_semine)


def _content(merged: dict[str, Any]) -> str:
    return (f"hydration_hours={merged['idratazione_ore']}; germination_days={merged['germinazione_giorni']}; "
            f"light_growth_days={merged['crescita_luce_giorni']}; seed_grams_per_set={merged['grammi_seme_per_set']}")


def _text(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, time):
        return value.isoformat()
    return value


def revise(cursor: Any, *, variety: str, changes: dict[str, Any], valid_from: date, today: date,
           actor: str, reason: str, evidence: str | None, correlation_id: str, provenance: str,
           now: datetime | None = None) -> Revision:
    for name, value in (("actor", actor), ("reason", reason), ("correlation_id", correlation_id),
                        ("provenance", provenance)):
        if not value or not value.strip():
            raise ProtocolRevisionError(f"{name} obbligatorio.")
    revision = prepare(cursor, variety, changes, valid_from, today, lock=True)
    old, now = revision.old, now or datetime.now(timezone.utc)
    merged = {**old, **revision.new_values}
    cursor.execute(
        "UPDATE tpo.protocollo_versioni SET valida_al=%s WHERE id=%s AND public_id=%s AND valida_al IS NULL",
        (valid_from, old["id"], old["public_id"]))
    if cursor.rowcount != 1:
        raise ProtocolRevisionError("Conflitto: la versione corrente e' cambiata nel frattempo, riprovare.")
    cursor.execute(
        """INSERT INTO tpo.audit_eventi
             (occurred_at,actor,entity_type,entity_public_id,operation,reason,before_data,after_data,
              correlation_id,provenance)
           VALUES (%s,%s,'PROTOCOLLO_VERSIONE',%s,'UPDATE',%s,%s::jsonb,%s::jsonb,%s,%s)""",
        (now, actor, old["public_id"],
         f"Chiusura versione superata dalla revisione {revision.new_public_id}: {reason}",
         json.dumps({"valida_al": None}), json.dumps({"valida_al": valid_from.isoformat()}),
         correlation_id, provenance))
    cursor.execute(
        """INSERT INTO tpo.protocollo_versioni
             (protocollo_id,numero_versione,valida_dal,valida_al,contenuto,motivazione,evidenze,public_id,
              stato_approvazione,idratazione_ore,orario_semina_previsto,orario_raccolta_target,
              germinazione_giorni,crescita_luce_giorni,grammi_seme_per_set,resa_attesa,resa_unita_misura,
              granularita_produttiva,harvest_min_lead_giorni,harvest_max_lead_giorni,buffer_temporale_minuti,
              provenance,approvata_at,approvata_by,created_by,versione_precedente_id)
           VALUES (%s,%s,%s,NULL,%s,%s,%s,%s,'APPROVATA',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (old["protocollo_id"], old["numero_versione"] + 1, valid_from, _content(merged), reason,
         evidence if evidence is not None else old["evidenze"], revision.new_public_id,
         merged["idratazione_ore"], merged["orario_semina_previsto"], merged["orario_raccolta_target"],
         merged["germinazione_giorni"], merged["crescita_luce_giorni"], merged["grammi_seme_per_set"],
         merged["resa_attesa"], merged["resa_unita_misura"], merged["granularita_produttiva"],
         merged["harvest_min_lead_giorni"], merged["harvest_max_lead_giorni"], merged["buffer_temporale_minuti"],
         provenance, now, actor, actor, old["id"]))
    payload = {
        "protocollo_id": old["protocollo_id"], "numero_versione": old["numero_versione"] + 1,
        "valida_dal": valid_from.isoformat(), "valida_al": None, "variety": old["variety"],
        "hydration_hours": str(merged["idratazione_ore"]),
        "planned_sowing_time": merged["orario_semina_previsto"].isoformat(),
        "target_harvest_time": merged["orario_raccolta_target"].isoformat(),
        "germination_days": merged["germinazione_giorni"], "light_growth_days": merged["crescita_luce_giorni"],
        "seed_grams_per_set": str(merged["grammi_seme_per_set"]), "expected_yield": str(merged["resa_attesa"]),
        "expected_yield_uom": merged["resa_unita_misura"],
        "production_granularity": str(merged["granularita_produttiva"]),
        "harvest_min_lead_days": merged["harvest_min_lead_giorni"],
        "harvest_max_lead_days": merged["harvest_max_lead_giorni"],
        "temporal_buffer_minutes": merged["buffer_temporale_minuti"], "provenance": provenance,
        "versione_precedente_public_id": old["public_id"],
        "changes": {name: {"from": _text(a), "to": _text(b)} for name, (a, b) in revision.changes.items()},
    }
    cursor.execute(
        """INSERT INTO tpo.audit_eventi
             (occurred_at,actor,entity_type,entity_public_id,operation,reason,after_data,correlation_id,provenance)
           VALUES (%s,%s,'PROTOCOLLO_VERSIONE',%s,'INSERT',%s,%s::jsonb,%s,%s)""",
        (now, actor, revision.new_public_id, reason, json.dumps(payload, sort_keys=True), correlation_id,
         provenance))
    return revision
