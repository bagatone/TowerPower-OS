from __future__ import annotations

import json
from datetime import timezone
from decimal import Decimal
from typing import Any

import psycopg

from ...application.agronomic_commissioning.errors import (
    AgronomicCommissioningConflictError,
    AgronomicCommissioningOutcomeUncertain,
    AgronomicCommissioningPersistenceError,
)
from ...application.agronomic_commissioning.models import CommissionedAgronomicProtocol
from .connection import PostgreSQLConnectionFactory


class PostgreSQLAgronomicProtocolCommissioningWriter:
    """Atomic, append-only commissioning for one complete production authority."""

    def __init__(self, connection_factory: PostgreSQLConnectionFactory) -> None:
        self._factory = connection_factory

    def commission(self, value: CommissionedAgronomicProtocol) -> CommissionedAgronomicProtocol:
        command = value.command
        connection = self._factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            inserted: list[str] = []
            cursor.execute(
                "SELECT id,denominazione,stato FROM tpo.varieta WHERE public_id=%s",
                (command.variety_id.value,),
            )
            variety = cursor.fetchone()
            if variety is None or variety[1:] != (command.variety_name, "ATTIVA"):
                raise AgronomicCommissioningConflictError("VARIETA assente o incompatibile.")

            use_id, was_inserted = self._productive_use(cursor, command)
            if was_inserted: inserted.append("USO_PRODUTTIVO")
            cultivar_id, was_inserted = self._cultivar(cursor, command, variety[0])
            if was_inserted: inserted.append("CULTIVAR")
            cultivar_use_id, was_inserted = self._cultivar_use(cursor, command, cultivar_id, use_id)
            if was_inserted: inserted.append("CULTIVAR_USO")
            protocol_id, was_inserted = self._protocol(cursor, command, cultivar_use_id)
            if was_inserted: inserted.append("PROTOCOLLO")
            approved_at, was_inserted = self._version(cursor, command, protocol_id, value.approved_at)
            payload = _payload(command)
            if was_inserted:
                inserted.append("PROTOCOLLO_VERSIONE")
                cursor.execute(
                    """INSERT INTO tpo.audit_eventi
                         (occurred_at,actor,entity_type,entity_public_id,operation,
                          reason,after_data,correlation_id)
                       VALUES (%s,%s,'PROTOCOLLO_VERSIONE',%s,'INSERT',%s,%s::jsonb,%s)""",
                    (approved_at, command.actor.value, command.protocol_version_id.value,
                     command.reason, json.dumps(payload, sort_keys=True), command.correlation_id),
                )
            else:
                self._assert_audit(cursor, command, payload)
            try:
                connection.commit()
            except Exception as exc:
                raise AgronomicCommissioningOutcomeUncertain("Esito commit agronomico da riconciliare.") from exc
            committed = True
            return CommissionedAgronomicProtocol(command, approved_at, tuple(inserted))
        except AgronomicCommissioningConflictError:
            raise
        except psycopg.IntegrityError as exc:
            raise AgronomicCommissioningConflictError("Vincolo agronomico non soddisfatto.") from exc
        except psycopg.Error as exc:
            raise AgronomicCommissioningPersistenceError("Commissioning agronomico PostgreSQL fallito.") from exc
        finally:
            if not committed:
                try: connection.rollback()
                except Exception: pass
            if cursor is not None:
                try: cursor.close()
                except Exception: pass
            try: connection.close()
            except Exception: pass

    @staticmethod
    def _productive_use(cursor: Any, command: Any) -> tuple[int, bool]:
        cursor.execute(
            """INSERT INTO tpo.usi_produttivi
                 (codice,denominazione,attivo,created_by,updated_at,updated_by,version)
               VALUES (%s,%s,TRUE,%s,CURRENT_TIMESTAMP,%s,0)
               ON CONFLICT (codice) DO NOTHING RETURNING id""",
            (command.productive_use_code, command.productive_use_name,
             command.actor.value, command.actor.value),
        )
        row = cursor.fetchone()
        if row is not None: return row[0], True
        cursor.execute("SELECT id,denominazione,attivo,created_by,updated_by,version FROM tpo.usi_produttivi WHERE codice=%s", (command.productive_use_code,))
        row = cursor.fetchone()
        if row is None or row[1:] != (command.productive_use_name, True, command.actor.value, command.actor.value, 0):
            raise AgronomicCommissioningConflictError("USO_PRODUTTIVO incompatibile.")
        return row[0], False

    @staticmethod
    def _cultivar(cursor: Any, command: Any, variety_id: int) -> tuple[int, bool]:
        cursor.execute("SELECT id,stato,created_by,updated_by,version FROM tpo.cultivar WHERE varieta_id=%s AND lower(btrim(denominazione))=lower(btrim(%s))", (variety_id, command.cultivar_name))
        row = cursor.fetchone()
        if row is not None:
            if row[1:] != ("ATTIVA", command.actor.value, command.actor.value, 0):
                raise AgronomicCommissioningConflictError("CULTIVAR incompatibile.")
            return row[0], False
        cursor.execute("""INSERT INTO tpo.cultivar(varieta_id,denominazione,stato,created_by,updated_at,updated_by,version)
                          VALUES (%s,%s,'ATTIVA',%s,CURRENT_TIMESTAMP,%s,0) RETURNING id""",
                       (variety_id, command.cultivar_name, command.actor.value, command.actor.value))
        return cursor.fetchone()[0], True

    @staticmethod
    def _cultivar_use(cursor: Any, command: Any, cultivar_id: int, use_id: int) -> tuple[int, bool]:
        cursor.execute("""INSERT INTO tpo.cultivar_usi
                          (cultivar_id,uso_produttivo_id,stato_validazione,created_by,updated_at,updated_by,version)
                          VALUES (%s,%s,'APPROVATA',%s,CURRENT_TIMESTAMP,%s,0)
                          ON CONFLICT (cultivar_id,uso_produttivo_id) DO NOTHING RETURNING id""",
                       (cultivar_id, use_id, command.actor.value, command.actor.value))
        row = cursor.fetchone()
        if row is not None: return row[0], True
        cursor.execute("SELECT id,stato_validazione,created_by,updated_by,version FROM tpo.cultivar_usi WHERE cultivar_id=%s AND uso_produttivo_id=%s", (cultivar_id, use_id))
        row = cursor.fetchone()
        if row is None or row[1:] != ("APPROVATA", command.actor.value, command.actor.value, 0):
            raise AgronomicCommissioningConflictError("CULTIVAR_USO incompatibile.")
        return row[0], False

    @staticmethod
    def _protocol(cursor: Any, command: Any, cultivar_use_id: int) -> tuple[int, bool]:
        cursor.execute("SELECT id,denominazione,attivo,created_by,updated_by,version FROM tpo.protocolli WHERE cultivar_uso_id=%s AND tipo='STANDARD'", (cultivar_use_id,))
        row = cursor.fetchone()
        if row is not None:
            if row[1:] != (command.protocol_name, True, command.actor.value, command.actor.value, 0):
                raise AgronomicCommissioningConflictError("PROTOCOLLO incompatibile.")
            return row[0], False
        cursor.execute("""INSERT INTO tpo.protocolli
                          (cultivar_uso_id,tipo,denominazione,attivo,created_by,updated_at,updated_by,version)
                          VALUES (%s,'STANDARD',%s,TRUE,%s,CURRENT_TIMESTAMP,%s,0) RETURNING id""",
                       (cultivar_use_id, command.protocol_name, command.actor.value, command.actor.value))
        return cursor.fetchone()[0], True

    @staticmethod
    def _version(cursor: Any, command: Any, protocol_id: int, approved_at: Any) -> tuple[Any, bool]:
        cursor.execute("SELECT id FROM tpo.protocollo_versioni WHERE public_id=%s OR (protocollo_id=%s AND numero_versione=%s) ORDER BY id", (command.protocol_version_id.value, protocol_id, command.version))
        identities = cursor.fetchall()
        if identities:
            if len(identities) != 1:
                raise AgronomicCommissioningConflictError("Identity versione protocollo ambigua.")
            cursor.execute("""SELECT protocollo_id,numero_versione,valida_dal,valida_al,contenuto,motivazione,evidenze,
                              public_id,stato_approvazione,idratazione_ore,orario_semina_previsto,
                              orario_raccolta_target,germinazione_giorni,crescita_luce_giorni,
                              grammi_seme_per_set,resa_attesa,resa_unita_misura,granularita_produttiva,
                              harvest_min_lead_giorni,harvest_max_lead_giorni,buffer_temporale_minuti,
                              provenance,approvata_at,approvata_by,ritirata_at,ritirata_by,created_by
                       FROM tpo.protocollo_versioni WHERE id=%s""", (identities[0][0],))
            row = cursor.fetchone()
            if not _compatible_version(command, protocol_id, row):
                raise AgronomicCommissioningConflictError("PROTOCOLLO_VERSIONE incompatibile.")
            return row[22], False
        cursor.execute("""INSERT INTO tpo.protocollo_versioni
                          (protocollo_id,numero_versione,valida_dal,valida_al,contenuto,motivazione,evidenze,
                           public_id,stato_approvazione,idratazione_ore,orario_semina_previsto,
                           orario_raccolta_target,germinazione_giorni,crescita_luce_giorni,
                           grammi_seme_per_set,resa_attesa,resa_unita_misura,granularita_produttiva,
                           harvest_min_lead_giorni,harvest_max_lead_giorni,buffer_temporale_minuti,
                           provenance,approvata_at,approvata_by,created_by)
                          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'APPROVATA',%s,%s,%s,%s,%s,%s,%s,'SET',%s,%s,%s,%s,%s,%s,%s,%s)
                          RETURNING approvata_at""",
                       (protocol_id, command.version, command.valid_from, command.valid_to, command.content,
                        command.motivation, command.evidence, command.protocol_version_id.value,
                        command.hydration_hours, command.planned_sowing_time, command.target_harvest_time,
                        command.germination_days, command.light_growth_days, command.seed_grams_per_set,
                        command.expected_yield, command.production_granularity, command.harvest_min_lead_days,
                        command.harvest_max_lead_days, command.temporal_buffer_minutes, command.provenance,
                        approved_at, command.actor.value, command.actor.value))
        return cursor.fetchone()[0], True

    @staticmethod
    def _assert_audit(cursor: Any, command: Any, payload: dict[str, Any]) -> None:
        cursor.execute("""SELECT actor,reason,after_data,correlation_id FROM tpo.audit_eventi
                          WHERE entity_type='PROTOCOLLO_VERSIONE' AND entity_public_id=%s AND operation='INSERT'
                          ORDER BY id""", (command.protocol_version_id.value,))
        rows = cursor.fetchall()
        if len(rows) != 1 or rows[0] != (command.actor.value, command.reason, payload, command.correlation_id):
            raise AgronomicCommissioningConflictError("Audit agronomico incompatibile.")


def _compatible_version(c: Any, protocol_id: int, r: tuple[Any, ...]) -> bool:
    expected = (protocol_id, c.version, c.valid_from, c.valid_to, c.content, c.motivation, c.evidence,
                c.protocol_version_id.value, "APPROVATA", c.hydration_hours, c.planned_sowing_time,
                c.target_harvest_time, c.germination_days, c.light_growth_days, c.seed_grams_per_set,
                c.expected_yield, "SET", c.production_granularity, c.harvest_min_lead_days,
                c.harvest_max_lead_days, c.temporal_buffer_minutes, c.provenance)
    return tuple(Decimal(x) if isinstance(x, Decimal) else x for x in r[:22]) == expected and r[23:] == (c.actor.value, None, None, c.actor.value)


def _payload(c: Any) -> dict[str, Any]:
    return {
        "variety_id": c.variety_id.value, "variety_name": c.variety_name,
        "cultivar_name": c.cultivar_name, "productive_use_code": c.productive_use_code,
        "protocol_name": c.protocol_name, "protocol_version_id": c.protocol_version_id.value,
        "version": c.version, "valid_from": c.valid_from.isoformat(), "valid_to": None,
        "hydration_hours": str(c.hydration_hours), "planned_sowing_time": c.planned_sowing_time.isoformat(),
        "target_harvest_time": c.target_harvest_time.isoformat(), "germination_days": c.germination_days,
        "light_growth_days": c.light_growth_days, "seed_grams_per_set": str(c.seed_grams_per_set),
        "expected_yield": str(c.expected_yield), "expected_yield_uom": "SET",
        "production_granularity": str(c.production_granularity),
        "harvest_min_lead_days": c.harvest_min_lead_days, "harvest_max_lead_days": c.harvest_max_lead_days,
        "temporal_buffer_minutes": c.temporal_buffer_minutes, "provenance": c.provenance,
    }
