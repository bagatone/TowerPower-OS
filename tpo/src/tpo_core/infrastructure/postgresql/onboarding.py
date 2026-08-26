"""Atomic PostgreSQL writer for governed operational-data onboarding."""

from __future__ import annotations

import json
from datetime import timezone
from typing import Any, Callable

import psycopg

from ...application.onboarding.errors import (
    OnboardingConflictError, OnboardingOutcomeUncertain, OnboardingPersistenceError,
)
from ...application.onboarding.models import (
    CommissionCustomer, CommissionSupplyProgram, CommissionVariety,
    CorrectNeverEffectiveSupplyProgramVersion, OnboardingResult,
)
from ...domain.entities.programma_fornitura import TipoRicorrenza
from .connection import PostgreSQLConnectionFactory


class PostgreSQLOperationalDataOnboardingWriter:
    def __init__(self, connection_factory: PostgreSQLConnectionFactory) -> None:
        self._factory = connection_factory

    def commission_customer(self, command: CommissionCustomer) -> OnboardingResult:
        payload = {"public_id": command.customer_id.value, "denominazione": command.denomination, "version": 0}

        def operation(cursor: Any) -> bool:
            cursor.execute(
                """INSERT INTO tpo.clienti
                     (public_id,denominazione,created_by,updated_at,updated_by,version)
                     VALUES (%s,%s,%s,CURRENT_TIMESTAMP,%s,0)
                     ON CONFLICT (public_id) DO NOTHING RETURNING id""",
                (command.customer_id.value, command.denomination,
                 command.authority.actor.value, command.authority.actor.value),
            )
            inserted = cursor.fetchone() is not None
            if not inserted:
                cursor.execute("SELECT denominazione,version FROM tpo.clienti WHERE public_id=%s", (command.customer_id.value,))
                if cursor.fetchone() != (command.denomination, 0):
                    raise OnboardingConflictError("CLIENTE esiste con payload differente.")
                self._assert_audit(cursor, "CLIENTE", command.customer_id.value, payload, command.authority)
            return inserted

        return self._execute("CLIENTE", command.customer_id.value, payload, command.authority, operation)

    def commission_variety(self, command: CommissionVariety) -> OnboardingResult:
        variety = command.variety
        payload = {"public_id": variety.id.value, "denominazione": variety.denominazione,
                   "stato": variety.stato.value,
                   "codice_tracciabilita": (variety.traceability_code.value
                                              if variety.traceability_code else None),
                   "version": 0}

        def operation(cursor: Any) -> bool | tuple[bool, bool]:
            cursor.execute(
                """INSERT INTO tpo.varieta
                     (public_id,denominazione,stato,codice_tracciabilita,created_by,updated_at,updated_by,version)
                     VALUES (%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,%s,0)
                     ON CONFLICT (public_id) DO NOTHING RETURNING id""",
                (variety.id.value, variety.denominazione, variety.stato.value,
                 variety.traceability_code.value if variety.traceability_code else None,
                 command.authority.actor.value, command.authority.actor.value),
            )
            inserted = cursor.fetchone() is not None
            if not inserted:
                cursor.execute("SELECT denominazione,stato,codice_tracciabilita,version FROM tpo.varieta WHERE public_id=%s FOR UPDATE", (variety.id.value,))
                existing = cursor.fetchone()
                requested = variety.traceability_code.value if variety.traceability_code else None
                if existing[:2] != (variety.denominazione, variety.stato.value):
                    raise OnboardingConflictError("VARIETA esiste con payload differente.")
                if existing[2] is None and requested is not None:
                    cursor.execute(
                        "UPDATE tpo.varieta SET codice_tracciabilita=%s,version=version+1,updated_at=CURRENT_TIMESTAMP,updated_by=%s WHERE public_id=%s AND codice_tracciabilita IS NULL AND version=%s",
                        (requested, command.authority.actor.value, variety.id.value, existing[3]),
                    )
                    if cursor.rowcount != 1:
                        raise OnboardingConflictError("Commissioning codice VARIETA concorrente.")
                    payload["version"] = existing[3] + 1
                    cursor.execute(
                        """INSERT INTO tpo.audit_eventi
                           (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                            before_data,after_data,correlation_id)
                           VALUES (CURRENT_TIMESTAMP,%s,'VARIETA',%s,'UPDATE',%s,%s::jsonb,%s::jsonb,%s)""",
                        (command.authority.actor.value, variety.id.value, command.authority.reason,
                         json.dumps({"codice_tracciabilita": None, "version": existing[3]}, sort_keys=True),
                         json.dumps(payload, sort_keys=True), command.authority.correlation_id),
                    )
                    return False, True
                if existing[2] != requested:
                    raise OnboardingConflictError("Codice di tracciabilita VARIETA differente.")
                payload["version"] = existing[3]
                if existing[3] == 0:
                    self._assert_audit(cursor, "VARIETA", variety.id.value, payload, command.authority)
                else:
                    cursor.execute(
                        """SELECT actor,reason,after_data,correlation_id FROM tpo.audit_eventi
                           WHERE entity_type='VARIETA' AND entity_public_id=%s
                             AND operation='UPDATE' ORDER BY id DESC LIMIT 1""",
                        (variety.id.value,),
                    )
                    audit = cursor.fetchone()
                    if (audit is None or audit[0] != command.authority.actor.value
                            or audit[1] != command.authority.reason or audit[2] != payload
                            or audit[3] != command.authority.correlation_id):
                        raise OnboardingConflictError("Provenance codice VARIETA differente.")
            return inserted

        return self._execute("VARIETA", variety.id.value, payload, command.authority, operation)

    def commission_supply_program(self, command: CommissionSupplyProgram) -> OnboardingResult:
        program = command.program
        lines = sorted(enumerate(program.righe, 1), key=lambda item: item[0])
        payload = {
            "public_id": program.id.value, "cliente_id": program.cliente_id.value,
            "version": command.version, "stato": program.stato.value,
            "data_inizio": program.data_inizio.isoformat(),
            "data_fine": program.data_fine.isoformat() if program.data_fine else None,
            "orario_generazione": program.orario_generazione.isoformat(),
            "finestra_operativa_giorni": program.finestra_operativa_giorni,
            "valida_dal": _instant(command.valid_from),
            "righe": [_line_payload(position, line) for position, line in lines],
        }

        def operation(cursor: Any) -> bool:
            cursor.execute("SELECT id FROM tpo.clienti WHERE public_id=%s", (program.cliente_id.value,))
            customer = cursor.fetchone()
            if customer is None:
                raise OnboardingConflictError("CLIENTE richiesto non esiste.")
            variety_ids: dict[str, int] = {}
            for _, line in lines:
                cursor.execute("SELECT id FROM tpo.varieta WHERE public_id=%s", (line.varieta_id.value,))
                row = cursor.fetchone()
                if row is None:
                    raise OnboardingConflictError("VARIETA richiesta non esiste.")
                variety_ids[line.varieta_id.value] = row[0]
            cursor.execute("SELECT id FROM tpo.programmi_fornitura WHERE public_id=%s", (program.id.value,))
            existing = cursor.fetchone()
            if existing is not None:
                if self._load_program(cursor, program.id.value) != payload:
                    raise OnboardingConflictError("PROGRAMMA_FORNITURA esiste con payload differente.")
                self._assert_audit(cursor, "PROGRAMMA_FORNITURA", program.id.value, payload, command.authority)
                return False
            cursor.execute(
                """INSERT INTO tpo.programmi_fornitura(public_id,cliente_id,created_by)
                   VALUES (%s,%s,%s) RETURNING id""",
                (program.id.value, customer[0], command.authority.actor.value),
            )
            program_pk = cursor.fetchone()[0]
            cursor.execute(
                """INSERT INTO tpo.programmi_fornitura_versioni
                   (programma_fornitura_id,cliente_id,numero_versione,stato,data_inizio,
                    data_fine,orario_generazione,finestra_operativa_giorni,valida_dal,
                    valida_al,created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s) RETURNING id""",
                (program_pk, customer[0], command.version, program.stato.value,
                 program.data_inizio, program.data_fine, program.orario_generazione,
                 program.finestra_operativa_giorni, command.valid_from,
                 command.authority.actor.value),
            )
            version_pk = cursor.fetchone()[0]
            for position, line in lines:
                cursor.execute(
                    """INSERT INTO tpo.righe_programma_fornitura
                       (programma_versione_id,posizione,varieta_id,quantita,unita_misura,
                        tipo_ricorrenza,intervallo_giorni)
                       VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (version_pk, position, variety_ids[line.varieta_id.value],
                     line.quantita.value, line.quantita.unit.value,
                     line.configurazione_temporale.tipo.value,
                     line.configurazione_temporale.intervallo_giorni),
                )
                line_pk = cursor.fetchone()[0]
                for day in sorted(line.configurazione_temporale.giorni_settimana):
                    cursor.execute("INSERT INTO tpo.righe_programma_giorni(riga_programma_id,giorno_iso) VALUES (%s,%s)", (line_pk, day))
            return True

        return self._execute("PROGRAMMA_FORNITURA", program.id.value, payload, command.authority, operation)

    def correct_never_effective_supply_program_version(
        self, command: CorrectNeverEffectiveSupplyProgramVersion
    ) -> OnboardingResult:
        program = command.program
        lines = tuple(enumerate(program.righe, 1))
        new_version = command.expected_current_version + 1
        payload = {
            "category": "NEVER_EFFECTIVE",
            "previous_version": command.expected_current_version,
            "corrected_version": new_version,
            "program": self._program_payload(program, new_version, command.valid_from, lines),
        }

        def operation(cursor: Any) -> bool:
            cursor.execute(
                """SELECT operation,after_data FROM tpo.audit_eventi
                   WHERE entity_type='PROGRAMMA_FORNITURA_VERSION_CORRECTION'
                     AND entity_public_id=%s AND correlation_id=%s
                   ORDER BY id""",
                (program.id.value, command.authority.correlation_id),
            )
            replay = cursor.fetchall()
            if replay:
                if len(replay) != 1 or replay[0] != ("STATE_TRANSITION", payload):
                    raise OnboardingConflictError("Replay correzione incompatibile.")
                cursor.execute(
                    """SELECT pv.numero_versione FROM tpo.programmi_fornitura p
                       JOIN tpo.programmi_fornitura_versioni pv
                         ON pv.programma_fornitura_id=p.id
                       WHERE p.public_id=%s AND pv.valida_al IS NULL
                         AND pv.voided_at IS NULL""", (program.id.value,),
                )
                if cursor.fetchone() != (new_version,):
                    raise OnboardingConflictError("Replay privo della versione corretta corrente.")
                return False

            cursor.execute(
                """SELECT p.id,p.cliente_id,pv.id,pv.numero_versione,pv.valida_dal,
                          pv.stato,pv.data_inizio,pv.data_fine,pv.orario_generazione,
                          pv.finestra_operativa_giorni
                   FROM tpo.programmi_fornitura p
                   JOIN tpo.programmi_fornitura_versioni pv
                     ON pv.programma_fornitura_id=p.id
                   WHERE p.public_id=%s AND pv.valida_al IS NULL
                     AND pv.voided_at IS NULL FOR UPDATE OF pv""", (program.id.value,),
            )
            current = cursor.fetchone()
            if current is None or current[3] != command.expected_current_version:
                raise OnboardingConflictError("Versione corrente attesa non disponibile.")
            if current[4] <= _database_now(cursor):
                raise OnboardingConflictError("La versione è già stata temporalmente efficace.")
            if current[1] is None:
                raise OnboardingConflictError("Autorità cliente del programma assente.")
            cursor.execute(
                """SELECT c.public_id FROM tpo.clienti c WHERE c.id=%s""", (current[1],),
            )
            if cursor.fetchone() != (program.cliente_id.value,):
                raise OnboardingConflictError("Cliente corretto differente dall'autorità corrente.")
            current_payload = self._load_program(cursor, program.id.value)
            expected_old = self._program_payload(
                program, command.expected_current_version, current[4], lines,
            )
            if current_payload != expected_old:
                raise OnboardingConflictError("La correzione altera il payload commerciale.")

            old_version_pk = current[2]
            cursor.execute(
                """SELECT EXISTS(
                     SELECT 1 FROM tpo.origini_righe_ordine oro
                     JOIN tpo.righe_programma_fornitura rp
                       ON rp.id=oro.riga_programma_id
                     WHERE rp.programma_versione_id=%s)""", (old_version_pk,),
            )
            if cursor.fetchone()[0]:
                raise OnboardingConflictError("La versione ha prodotto ORDINI/downstream effects.")

            cursor.execute(
                """UPDATE tpo.programmi_fornitura_versioni
                   SET voided_at=CURRENT_TIMESTAMP,voided_by=%s,void_reason=%s,
                       void_correlation_id=%s
                   WHERE id=%s AND voided_at IS NULL""",
                (command.authority.actor.value, command.authority.reason,
                 command.authority.correlation_id, old_version_pk),
            )
            if cursor.rowcount != 1:
                raise OnboardingConflictError("Conflitto concorrente sulla versione corrente.")
            cursor.execute(
                """INSERT INTO tpo.programmi_fornitura_versioni
                   (programma_fornitura_id,cliente_id,numero_versione,stato,data_inizio,
                    data_fine,orario_generazione,finestra_operativa_giorni,valida_dal,
                    valida_al,created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s) RETURNING id""",
                (current[0], current[1], new_version, program.stato.value,
                 program.data_inizio, program.data_fine, program.orario_generazione,
                 program.finestra_operativa_giorni, command.valid_from,
                 command.authority.actor.value),
            )
            replacement_pk = cursor.fetchone()[0]
            variety_ids: dict[str, int] = {}
            for _, line in lines:
                cursor.execute("SELECT id FROM tpo.varieta WHERE public_id=%s", (line.varieta_id.value,))
                row = cursor.fetchone()
                if row is None:
                    raise OnboardingConflictError("VARIETA richiesta non esiste.")
                variety_ids[line.varieta_id.value] = row[0]
            for position, line in lines:
                cursor.execute(
                    """INSERT INTO tpo.righe_programma_fornitura
                       (programma_versione_id,posizione,varieta_id,quantita,unita_misura,
                        tipo_ricorrenza,intervallo_giorni)
                       VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (replacement_pk, position, variety_ids[line.varieta_id.value],
                     line.quantita.value, line.quantita.unit.value,
                     line.configurazione_temporale.tipo.value,
                     line.configurazione_temporale.intervallo_giorni),
                )
                line_pk = cursor.fetchone()[0]
                for day in sorted(line.configurazione_temporale.giorni_settimana):
                    cursor.execute(
                        "INSERT INTO tpo.righe_programma_giorni(riga_programma_id,giorno_iso) VALUES (%s,%s)",
                        (line_pk, day),
                    )
            cursor.execute(
                "UPDATE tpo.programmi_fornitura_versioni SET replacement_version_id=%s WHERE id=%s",
                (replacement_pk, old_version_pk),
            )
            cursor.execute(
                """INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                    before_data,after_data,correlation_id,provenance)
                   VALUES (CURRENT_TIMESTAMP,%s,'PROGRAMMA_FORNITURA_VERSION_CORRECTION',
                           %s,'STATE_TRANSITION',%s,%s::jsonb,%s::jsonb,%s,
                           'never-effective-correction')""",
                (command.authority.actor.value, program.id.value,
                 command.authority.reason,
                 json.dumps({"previous_version": command.expected_current_version}, sort_keys=True),
                 json.dumps(payload, sort_keys=True), command.authority.correlation_id),
            )
            return True

        return self._execute(
            "PROGRAMMA_FORNITURA_VERSION_CORRECTION", program.id.value,
            payload, command.authority, operation, write_insert_audit=False,
        )

    @staticmethod
    def _program_payload(program: Any, version: int, valid_from: Any,
                         lines: tuple[tuple[int, Any], ...]) -> dict[str, Any]:
        return {
            "public_id": program.id.value, "cliente_id": program.cliente_id.value,
            "version": version, "stato": program.stato.value,
            "data_inizio": program.data_inizio.isoformat(),
            "data_fine": program.data_fine.isoformat() if program.data_fine else None,
            "orario_generazione": program.orario_generazione.isoformat(),
            "finestra_operativa_giorni": program.finestra_operativa_giorni,
            "valida_dal": _instant(valid_from),
            "righe": [_line_payload(position, line) for position, line in lines],
        }

    @staticmethod
    def _assert_audit(cursor: Any, entity_type: str, public_id: str,
                      payload: dict[str, Any], authority: Any) -> None:
        cursor.execute(
            """SELECT actor,reason,after_data,correlation_id
               FROM tpo.audit_eventi
               WHERE entity_type=%s AND entity_public_id=%s AND operation='INSERT'
               ORDER BY id LIMIT 1""", (entity_type, public_id))
        row = cursor.fetchone()
        if row is None or row[0] != authority.actor.value or row[1] != authority.reason \
                or row[2] != payload or row[3] != authority.correlation_id:
            raise OnboardingConflictError("Provenance onboarding esistente differente.")

    def _load_program(self, cursor: Any, public_id: str) -> dict[str, Any]:
        cursor.execute(
            """SELECT p.public_id,c.public_id,pv.numero_versione,pv.stato,pv.data_inizio,
                      pv.data_fine,pv.orario_generazione,pv.finestra_operativa_giorni,pv.valida_dal
               FROM tpo.programmi_fornitura p JOIN tpo.clienti c ON c.id=p.cliente_id
               JOIN tpo.programmi_fornitura_versioni pv ON pv.programma_fornitura_id=p.id
               WHERE p.public_id=%s AND pv.valida_al IS NULL""", (public_id,))
        row = cursor.fetchone()
        if row is None:
            return {}
        cursor.execute(
            """SELECT rp.posizione,v.public_id,rp.quantita,rp.unita_misura,
                      rp.tipo_ricorrenza,rp.intervallo_giorni,
                      ARRAY(SELECT giorno_iso FROM tpo.righe_programma_giorni g
                            WHERE g.riga_programma_id=rp.id ORDER BY giorno_iso)
               FROM tpo.righe_programma_fornitura rp JOIN tpo.varieta v ON v.id=rp.varieta_id
               JOIN tpo.programmi_fornitura_versioni pv ON pv.id=rp.programma_versione_id
               JOIN tpo.programmi_fornitura p ON p.id=pv.programma_fornitura_id
               WHERE p.public_id=%s AND pv.valida_al IS NULL ORDER BY rp.posizione""", (public_id,))
        line_rows = cursor.fetchall()
        return {
            "public_id": row[0], "cliente_id": row[1], "version": row[2], "stato": row[3],
            "data_inizio": row[4].isoformat(), "data_fine": row[5].isoformat() if row[5] else None,
            "orario_generazione": row[6].isoformat(), "finestra_operativa_giorni": row[7],
            "valida_dal": _instant(row[8]),
            "righe": [{"posizione": x[0], "varieta_id": x[1], "quantita": _decimal(x[2]),
                       "unita_misura": x[3], "tipo_ricorrenza": x[4],
                       "intervallo_giorni": x[5], "giorni_settimana": list(x[6])} for x in line_rows],
        }

    def _execute(self, entity_type: str, public_id: str, payload: dict[str, Any], authority: Any,
                 operation: Callable[[Any], bool | tuple[bool, bool]], *,
                 write_insert_audit: bool = True) -> OnboardingResult:
        connection = self._factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            operation_result = operation(cursor)
            if isinstance(operation_result, tuple):
                inserted, updated = operation_result
            else:
                inserted, updated = operation_result, False
            if inserted and write_insert_audit:
                cursor.execute(
                    """INSERT INTO tpo.audit_eventi
                       (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                        after_data,correlation_id)
                       VALUES (CURRENT_TIMESTAMP,%s,%s,%s,'INSERT',%s,%s::jsonb,%s)""",
                    (authority.actor.value, entity_type, public_id, authority.reason,
                     json.dumps(payload, sort_keys=True), authority.correlation_id),
                )
            try:
                connection.commit()
            except Exception as exc:
                raise OnboardingOutcomeUncertain("Esito commit onboarding da riconciliare.") from exc
            committed = True
            return OnboardingResult(entity_type, public_id, inserted, updated)
        except OnboardingConflictError:
            raise
        except psycopg.IntegrityError as exc:
            raise OnboardingConflictError("Vincolo onboarding non soddisfatto.") from exc
        except psycopg.Error as exc:
            raise OnboardingPersistenceError("Onboarding PostgreSQL fallito con rollback certo.") from exc
        finally:
            if not committed:
                try: connection.rollback()
                except Exception: pass
            if cursor is not None:
                try: cursor.close()
                except Exception: pass
            try: connection.close()
            except Exception: pass


def _line_payload(position: int, line: Any) -> dict[str, Any]:
    temporal = line.configurazione_temporale
    return {"posizione": position, "varieta_id": line.varieta_id.value,
            "quantita": _decimal(line.quantita.value), "unita_misura": line.quantita.unit.value,
            "tipo_ricorrenza": temporal.tipo.value,
            "intervallo_giorni": temporal.intervallo_giorni,
            "giorni_settimana": list(sorted(temporal.giorni_settimana))}


def _decimal(value: Any) -> str:
    return format(value.normalize(), "f")


def _instant(value: Any) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _database_now(cursor: Any) -> Any:
    cursor.execute("SELECT CURRENT_TIMESTAMP")
    return cursor.fetchone()[0]
