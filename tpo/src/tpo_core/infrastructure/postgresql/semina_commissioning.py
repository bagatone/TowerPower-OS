"""Writer PostgreSQL atomico per Semina Commissioning Boundary V1."""
from __future__ import annotations

import json
from zoneinfo import ZoneInfo
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.semina_commissioning.errors import (
    AnomalousSeedLotError, ExpiredSeedLotError, IncompatibleSeedLotError,
    InsufficientSeedError, PlanningLineNotFoundError, PlanningLineStateError,
    PlanningLineVersionConflictError, PlanningQuantityExceededError,
    ProtocolContextIncompatibleError, ProtocolUnavailableError,
    SeedLotNotFoundError, SeedLotVersionConflictError, SeminaCommitOutcomeUncertainError,
    SeminaCommitRolledBackError, SeminaIdempotencyConflictError,
    SeminaIdentityUnavailableError, SeminaReconciliationRequiredError,
    TraceabilityCodeConflictError, TraceabilityDiscriminatorExhaustedError,
    VarietyTraceabilityCodeUnavailableError,
)
from ...application.semina_commissioning.models import (
    CommissionSemina, CommissionSeminaResult, SeminaOrigin,
)
from ...domain.identifiers import LottoSemeId, RigaPianoSeminaId, SeminaId
from ...domain.quantities import Quantity, UnitOfMeasure
from ...domain.traceability import SeminaTraceabilityCode, VarietyTraceabilityCode
from .connection import PostgreSQLConnectionFactory

SCOPE = "SEMINA_COMMISSIONING_V1"
CANARY = ZoneInfo("Atlantic/Canary")


class PostgreSQLSeminaCommissioningWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def commission(self, command: CommissionSemina) -> CommissionSeminaResult:
        connection = self._factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            reservation, replay = self._reserve_or_replay(cursor, command)
            if replay is not None:
                connection.rollback()
                return replay
            if reservation is None:
                raise SeminaReconciliationRequiredError("Reservation non riconciliabile.")
            lot = self._lot(cursor, command)
            context = self._context(cursor, command, lot[1])
            planning = self._planning(cursor, command, context) if command.planning_start else None
            public_id, sequence = self._allocate(cursor)
            traceability_code = self._allocate_traceability(cursor, context[14], command.physical_started_at)
            cursor.execute(
                """INSERT INTO tpo.semine
                (public_id,varieta_id,cultivar_id,cultivar_uso_id,lotto_seme_id,
                 protocollo_versione_id,stato,quantita_seme,unita_misura,data_avvio,
                 causa_origine,esito_finale,cultivar_snapshot,uso_produttivo_snapshot,
                 lotto_seme_snapshot,protocollo_snapshot,created_by,version,
                 expected_useful_quantity,expected_useful_uom,harvest_window_start,harvest_window_end,
                 codice_tracciabilita)
                VALUES (%s,%s,%s,%s,%s,%s,'AVVIATA',%s,'GRAM',%s,%s,NULL,%s,%s,%s,%s,%s,0,
                        NULL,NULL,NULL,NULL,%s)
                RETURNING id,created_at""",
                (public_id.value, context[1], context[2], context[3], lot[0], context[0],
                 command.actual_seed_quantity.value, command.physical_started_at,
                 command.origin.value, context[5], context[6], command.seed_lot_public_id.value,
                 command.protocol_version_public_id.value, command.authority.actor.value,
                 traceability_code.value),
            )
            semina_pk, recorded_at = cursor.fetchone()
            new_residual = lot[2] - command.actual_seed_quantity.value
            cursor.execute(
                """UPDATE tpo.lotti_seme SET quantita_residua=%s,version=version+1,
                   updated_at=%s,updated_by=%s WHERE id=%s AND version=%s
                   AND quantita_residua=%s AND quantita_residua>=%s""",
                (new_residual, recorded_at, command.authority.actor.value, lot[0], lot[3],
                 lot[2], command.actual_seed_quantity.value),
            )
            if cursor.rowcount != 1:
                raise SeedLotVersionConflictError("LSE modificato concorrente.")
            new_planning_version = None
            if planning is not None:
                started = command.planning_start.started_quantity.value
                cursor.execute(
                    """INSERT INTO tpo.righe_piano_semina_semine
                       (riga_piano_semina_id,semina_id,quantita_avviata,unita_misura,created_by)
                       VALUES (%s,%s,%s,'SET',%s)""",
                    (planning[0], semina_pk, started, command.authority.actor.value),
                )
                cursor.execute(
                    """UPDATE tpo.righe_piano_semina
                       SET quantita_avviata=quantita_avviata+%s,
                           quantita_residua_da_avviare=quantita_residua_da_avviare-%s,
                           stato='AVVIATA',version=version+1,updated_at=%s,updated_by=%s
                       WHERE id=%s AND version=%s AND stato IN ('PRONTA','AVVIATA')
                         AND quantita_residua_da_avviare>=%s""",
                    (started, started, recorded_at, command.authority.actor.value,
                     planning[0], planning[2], started),
                )
                if cursor.rowcount != 1:
                    raise PlanningLineVersionConflictError("RPS modificata concorrente.")
                new_planning_version = planning[2] + 1
            self._audit(cursor, public_id, traceability_code, semina_pk, command, lot, new_residual,
                        planning, new_planning_version, recorded_at)
            cursor.execute(
                """UPDATE tpo.semina_commissioning_requests
                   SET semina_id=%s,result_public_id=%s,outcome='COMMITTED',recorded_at=%s
                   WHERE id=%s AND outcome='RESERVED' AND canonical_payload_hash=%s""",
                (semina_pk, public_id.value, recorded_at, reservation,
                 command.canonical_payload_hash),
            )
            if cursor.rowcount != 1:
                raise SeminaReconciliationRequiredError("Reservation non aggiornabile.")
            cursor.execute(
                """UPDATE tpo.id_sequences SET next_value=%s,version=version+1,
                   updated_at=%s,updated_by=%s WHERE sequence_name=%s
                   AND identifier_type=%s AND prefix=%s AND next_value=%s AND version=%s""",
                (sequence[3] + 1, recorded_at, command.authority.actor.value,
                 SeminaId.sequence_name, SeminaId.__name__, SeminaId.prefix,
                 sequence[3], sequence[4]),
            )
            if cursor.rowcount != 1:
                raise SeminaIdentityUnavailableError("Conflitto contatore SEMINA_ID.")
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            result = CommissionSeminaResult(
                public_id, traceability_code, "INSERTED", "AVVIATA", command.seed_lot_public_id, lot[3] + 1,
                Quantity(new_residual, UnitOfMeasure.GRAM),
                command.planning_start.planning_line_public_id if planning else None,
                new_planning_version, recorded_at,
            )
            try:
                connection.commit()
            except Exception as exc:
                raise SeminaCommitOutcomeUncertainError(
                    "Esito commit SEMINA da riconciliare."
                ) from exc
            committed = True
            return result
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except psycopg.Error as exc:
            raise SeminaCommitRolledBackError("Commissioning SEMINA fallito con rollback certo.") from exc
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
    def _reserve_or_replay(cursor: Any, command: CommissionSemina):
        cursor.execute(
            """INSERT INTO tpo.semina_commissioning_requests
               (operation_scope,idempotency_key,canonical_payload_hash,semina_id,
                result_public_id,outcome,recorded_at,created_by)
               VALUES (%s,%s,%s,NULL,NULL,'RESERVED',CURRENT_TIMESTAMP,%s)
               ON CONFLICT (operation_scope,idempotency_key) DO NOTHING RETURNING id""",
            (SCOPE, command.authority.idempotency_key, command.canonical_payload_hash,
             command.authority.actor.value),
        )
        row = cursor.fetchone()
        if row:
            return row[0], None
        cursor.execute(
            """SELECT r.canonical_payload_hash,r.outcome,s.public_id,s.codice_tracciabilita,l.public_id,l.version,
                      l.quantita_residua,rps.public_id,rps.version,r.recorded_at
               FROM tpo.semina_commissioning_requests r
               JOIN tpo.semine s ON s.id=r.semina_id
               JOIN tpo.lotti_seme l ON l.id=s.lotto_seme_id
               LEFT JOIN tpo.righe_piano_semina_semine link ON link.semina_id=s.id
               LEFT JOIN tpo.righe_piano_semina rps ON rps.id=link.riga_piano_semina_id
               WHERE r.operation_scope=%s AND r.idempotency_key=%s FOR UPDATE OF r""",
            (SCOPE, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if not row:
            raise SeminaReconciliationRequiredError("Reservation concorrente non leggibile.")
        if row[0] != command.canonical_payload_hash:
            raise SeminaIdempotencyConflictError("Stessa idempotency key con payload differente.")
        if row[1] != "COMMITTED":
            raise SeminaReconciliationRequiredError("Reservation priva di risultato committed.")
        return None, CommissionSeminaResult(
            SeminaId(row[2]), SeminaTraceabilityCode(row[3]), "COMPATIBLE_REPLAY", "AVVIATA",
            LottoSemeId(row[4]), row[5], Quantity(row[6], UnitOfMeasure.GRAM),
            RigaPianoSeminaId(row[7]) if row[7] else None, row[8], row[9],
        )

    @staticmethod
    def _lot(cursor: Any, command: CommissionSemina):
        cursor.execute(
            """SELECT l.id,l.semente_id,l.quantita_residua,l.version,l.data_scadenza,l.anomalia
               FROM tpo.lotti_seme l WHERE l.public_id=%s FOR UPDATE""",
            (command.seed_lot_public_id.value,),
        )
        row = cursor.fetchone()
        if not row: raise SeedLotNotFoundError("LSE inesistente.")
        if row[3] != command.expected_seed_lot_version:
            raise SeedLotVersionConflictError("Versione LSE non corrente.")
        if row[5] is not None: raise AnomalousSeedLotError("LSE con anomalia non eleggibile.")
        business_date = command.physical_started_at.astimezone(CANARY).date()
        if row[4] is not None and row[4] < business_date:
            raise ExpiredSeedLotError("LSE scaduto alla data fisica di avvio.")
        if row[2] < command.actual_seed_quantity.value:
            raise InsufficientSeedError("Quantità residua LSE insufficiente.")
        return row

    @staticmethod
    def _context(cursor: Any, command: CommissionSemina, seed_id: int):
        business_date = command.physical_started_at.astimezone(CANARY).date()
        cursor.execute(
            """SELECT pv.id,v.id,c.id,cu.id,v.public_id,c.denominazione,u.denominazione,
                      p.tipo,p.attivo,cu.stato_validazione,c.stato,v.stato,u.attivo,s.attiva,
                      v.codice_tracciabilita
               FROM tpo.protocollo_versioni pv
               JOIN tpo.protocolli p ON p.id=pv.protocollo_id
               JOIN tpo.cultivar_usi cu ON cu.id=p.cultivar_uso_id
               JOIN tpo.cultivar c ON c.id=cu.cultivar_id
               JOIN tpo.varieta v ON v.id=c.varieta_id
               JOIN tpo.usi_produttivi u ON u.id=cu.uso_produttivo_id
               JOIN tpo.sementi s ON s.id=%s
               WHERE pv.public_id=%s AND pv.stato_approvazione='APPROVATA'
                 AND pv.valida_dal<=%s AND (pv.valida_al IS NULL OR pv.valida_al>%s)
               FOR SHARE OF pv,p,cu,c,v,u,s""",
            (seed_id, command.protocol_version_public_id.value, business_date, business_date),
        )
        rows = cursor.fetchall()
        if len(rows) != 1: raise ProtocolUnavailableError("PV assente, non approvata o non valida.")
        row = rows[0]
        if not row[13]:
            raise IncompatibleSeedLotError("SEMENTE inattiva per il LSE selezionato.")
        if row[7] != "STANDARD":
            raise ProtocolContextIncompatibleError("PROTOCOLLO non STANDARD non eleggibile.")
        if (not row[8] or row[9] != "APPROVATA" or row[10] != "ATTIVA"
                or row[11] != "ATTIVA" or not row[12]):
            raise ProtocolContextIncompatibleError("Contesto PV inattivo o non approvato.")
        cursor.execute(
            """SELECT raccomandazione FROM tpo.semente_impieghi
               WHERE semente_id=%s AND cultivar_uso_id=%s FOR SHARE""", (seed_id, row[3]),
        )
        uses = cursor.fetchall()
        if len(uses) != 1 or uses[0][0] not in ("RACCOMANDATA", "UTILIZZABILE"):
            raise IncompatibleSeedLotError("LSE/SEMENTE incompatibile con il contesto PV.")
        if row[14] is None:
            raise VarietyTraceabilityCodeUnavailableError(
                "VARIETA priva di codice di tracciabilita owner-authorized."
            )
        VarietyTraceabilityCode(row[14])
        return row

    @staticmethod
    def _planning(cursor: Any, command: CommissionSemina, context: Any):
        start = command.planning_start
        cursor.execute(
            """SELECT r.id,r.stato,r.version,r.quantita_avviata,r.quantita_residua_da_avviare,
                      r.quantita_produttiva_autorizzata,r.protocollo_versione_id,r.varieta_id,
                      r.cultivar_id,r.cultivar_uso_id
               FROM tpo.righe_piano_semina r
               JOIN tpo.piano_produzione_revisioni rv ON rv.id=r.piano_revisione_id
               JOIN tpo.piani_produzione pp ON pp.id=rv.piano_produzione_id
                 AND pp.current_revision_id=rv.id
               WHERE r.public_id=%s FOR UPDATE OF pp,rv,r""",
            (start.planning_line_public_id.value,),
        )
        row = cursor.fetchone()
        if not row: raise PlanningLineNotFoundError("RPS corrente inesistente.")
        if row[2] != start.expected_planning_line_version:
            raise PlanningLineVersionConflictError("Versione RPS non corrente.")
        if row[1] not in ("PRONTA", "AVVIATA"):
            raise PlanningLineStateError("Stato RPS non eleggibile.")
        if start.started_quantity.value > row[4]:
            raise PlanningQuantityExceededError("Quantità avviata eccede il residuo RPS.")
        if (row[6], row[7], row[8], row[9]) != (context[0], context[1], context[2], context[3]):
            raise ProtocolContextIncompatibleError("Contesto RPS non coincide con PV.")
        return row

    @staticmethod
    def _allocate(cursor: Any):
        cursor.execute("SELECT sequence_name,identifier_type,prefix,next_value,version FROM tpo.id_sequences WHERE sequence_name=%s FOR UPDATE", (SeminaId.sequence_name,))
        row = cursor.fetchone()
        if not row or row[1] != SeminaId.__name__ or row[2] != SeminaId.prefix:
            raise SeminaIdentityUnavailableError("SEMINA_ID assente o incompatibile.")
        return SeminaId(f"{row[2]}-{row[3]:06d}"), row

    @staticmethod
    def _allocate_traceability(cursor: Any, raw_variety_code: str, started_at: Any):
        variety_code = VarietyTraceabilityCode(raw_variety_code)
        local_date = started_at.astimezone(CANARY).date()
        scope = f"{variety_code.value}:{local_date.isoformat()}"
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (scope,))
        stem = f"{variety_code.value}-{local_date:%d%m}-"
        cursor.execute(
            "SELECT codice_tracciabilita FROM tpo.semine WHERE codice_tracciabilita LIKE %s",
            (stem + "%",),
        )
        used = {row[0][-1] for row in cursor.fetchall()}
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if letter not in used:
                return SeminaTraceabilityCode.build(variety_code, started_at, letter)
        raise TraceabilityDiscriminatorExhaustedError(
            f"Discriminatori A..Z esauriti per {scope}."
        )

    @staticmethod
    def _audit(cursor: Any, sem_id: SeminaId, traceability_code: SeminaTraceabilityCode,
               sem_pk: int, command: CommissionSemina,
               lot: Any, new_residual: Any, planning: Any, new_planning_version: Any,
               recorded_at: Any) -> None:
        provenance = {k: v.value for k, v in command.provenance}
        common = (recorded_at, command.authority.actor.value, command.authority.reason,
                  command.authority.correlation_id)
        events = [
            ("SEMINA", sem_id.value, "INSERT", None, {"public_id": sem_id.value,
             "traceability_code": traceability_code.value,
             "state": "AVVIATA", "seed_lot": command.seed_lot_public_id.value,
             "protocol_version": command.protocol_version_public_id.value,
             "actual_seed_grams": str(command.actual_seed_quantity.value),
             "physical_started_at": command.physical_started_at.isoformat(),
             "origin": command.origin.value, "predictive_authority": None}),
            ("LOTTO_SEME", command.seed_lot_public_id.value, "UPDATE",
             {"remaining": str(lot[2]), "version": lot[3]},
             {"remaining": str(new_residual), "version": lot[3] + 1}),
        ]
        if planning is not None:
            amount = command.planning_start.started_quantity.value
            events.append(("RIGA_PIANO_SEMINA", command.planning_start.planning_line_public_id.value,
                           "UPDATE", {"started": str(planning[3]), "residual": str(planning[4]),
                                      "state": planning[1], "version": planning[2]},
                           {"started": str(planning[3] + amount), "residual": str(planning[4] - amount),
                            "state": "AVVIATA", "version": new_planning_version,
                            "semina": sem_id.value, "started_quantity_set": str(amount)}))
        for entity, public, operation, before, after in events:
            cursor.execute(
                """INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                    before_data,after_data,correlation_id,provenance)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (common[0], common[1], entity, public, operation, common[2],
                 Jsonb(before) if before else None, Jsonb(after), common[3],
                 json.dumps({"boundary": "semina-commissioning-v1", "facts": provenance}, sort_keys=True)),
            )

    @staticmethod
    def _integrity_error(exc: psycopg.IntegrityError) -> Exception:
        name = getattr(exc.diag, "constraint_name", "")
        if name == "uq_semina_commissioning_request_key":
            return SeminaReconciliationRequiredError("Collisione idempotency da riconciliare.")
        if name in {"uq_semine_public_id", "ck_semine_public_id_format"}:
            return SeminaIdentityUnavailableError("Collisione SEM identity.")
        if name in {"uq_semine_codice_tracciabilita", "ck_semine_codice_tracciabilita"}:
            return TraceabilityCodeConflictError("Collisione codice di tracciabilita SEMINA.")
        if name.startswith("uq_righe_piano_semina_semine"):
            return ProtocolContextIncompatibleError("Link Planning non valido o duplicato.")
        return SeminaCommitRolledBackError("Vincolo SEMINA non soddisfatto.")
