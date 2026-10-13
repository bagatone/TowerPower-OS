"""Writer PostgreSQL atomico per PAGAMENTO CONSEGNA V1 (registra / annulla).

Idempotenza nella riga stessa (chiave univoca + hash del payload). La CONSEGNA
viene bloccata per serializzare due registrazioni concorrenti sulla stessa
consegna; l'identita' PGC si alloca da tpo.id_sequences con controllo di versione.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.pagamento_consegna.errors import (
    PagamentoConsegnaCommitOutcomeUncertainError, PagamentoConsegnaCommitRolledBackError,
    PagamentoConsegnaGiaAnnullatoError, PagamentoConsegnaGiaPagataError,
    PagamentoConsegnaIdempotencyConflictError, PagamentoConsegnaIdentityUnavailableError,
    PagamentoConsegnaNonConsegnataError, PagamentoConsegnaNonTrovataError,
    PagamentoConsegnaOriginaleNonTrovatoError, PagamentoConsegnaPersistenceInvariantError,
    PagamentoConsegnaReconciliationRequiredError,
)
from ...application.pagamento_consegna.models import (
    AnnullaPagamentoConsegna, AnnullaPagamentoConsegnaResult, RegistraPagamentoConsegna,
    RegistraPagamentoConsegnaResult,
)
from ...domain.identifiers import ConsegnaId, PagamentoConsegnaId
from ...domain.states import MetodoPagamento
from .connection import PostgreSQLConnectionFactory

_IDEMPOTENCY_CONSTRAINT = "pagamenti_consegna_idempotency_key_key"


class PostgreSQLPagamentoConsegnaWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    # ------------------------------------------------------------------ registra
    def record(self, command: RegistraPagamentoConsegna) -> RegistraPagamentoConsegnaResult:
        return self._run(command, self._record_once)

    def _record_once(self, cursor: Any, command: RegistraPagamentoConsegna):
        replay = self._replay(cursor, command.authority.idempotency_key,
                              command.canonical_payload_hash, "PAGAMENTO")
        if replay is not None:
            return replay
        consegna_pk = self._lock_consegna(cursor, command.consegna_id)
        replay = self._replay(cursor, command.authority.idempotency_key,
                              command.canonical_payload_hash, "PAGAMENTO")
        if replay is not None:      # richiesta identica conclusa mentre attendevo il lock
            return replay
        cursor.execute(
            """SELECT p.public_id FROM tpo.pagamenti_consegna p
               WHERE p.consegna_id=%s AND p.tipo='PAGAMENTO'
                 AND NOT EXISTS (SELECT 1 FROM tpo.pagamenti_consegna a
                                 WHERE a.annulla_pagamento_id=p.id)""",
            (consegna_pk,),
        )
        active = cursor.fetchone()
        if active:
            raise PagamentoConsegnaGiaPagataError(
                f"{command.consegna_id.value} risulta gia' pagata ({active[0]}): "
                "annullare prima quel pagamento."
            )
        public_id, sequence = self._allocate(cursor)
        authority = command.authority
        cursor.execute(
            """INSERT INTO tpo.pagamenti_consegna
               (public_id,consegna_id,tipo,data_pagamento,metodo,importo,note,storico,
                idempotency_key,payload_hash,reason,correlation_id,created_by)
               VALUES (%s,%s,'PAGAMENTO',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING created_at""",
            (public_id.value, consegna_pk, command.data_pagamento, command.metodo.value,
             command.importo, command.note, command.storico, authority.idempotency_key,
             command.canonical_payload_hash, authority.reason, authority.correlation_id,
             authority.actor.value),
        )
        recorded_at = cursor.fetchone()[0]
        after = {
            "public_id": public_id.value, "consegna": command.consegna_id.value,
            "data_pagamento": command.data_pagamento.isoformat(),
            "metodo": command.metodo.value,
            "importo": None if command.importo is None else str(command.importo),
            "storico": command.storico, "note": command.note,
            "recorded_at": recorded_at.isoformat(),
        }
        self._audit(cursor, recorded_at, authority, public_id.value, "INSERT", None, after,
                    "pagamento-consegna-registra-v1")
        self._bump(cursor, sequence, recorded_at, authority.actor.value)
        return RegistraPagamentoConsegnaResult(
            public_id, command.consegna_id, command.data_pagamento, command.metodo,
            command.importo, command.storico, recorded_at, "INSERTED",
        )

    # ------------------------------------------------------------------- annulla
    def cancel(self, command: AnnullaPagamentoConsegna) -> AnnullaPagamentoConsegnaResult:
        return self._run(command, self._cancel_once)

    def _cancel_once(self, cursor: Any, command: AnnullaPagamentoConsegna):
        replay = self._replay(cursor, command.authority.idempotency_key,
                              command.canonical_payload_hash, "ANNULLAMENTO")
        if replay is not None:
            return replay
        cursor.execute(
            """SELECT p.id,p.tipo,c.id,c.public_id FROM tpo.pagamenti_consegna p
               JOIN tpo.consegne c ON c.id=p.consegna_id
               WHERE p.public_id=%s FOR UPDATE OF p""",
            (command.pagamento_id.value,),
        )
        row = cursor.fetchone()
        replay = self._replay(cursor, command.authority.idempotency_key,
                              command.canonical_payload_hash, "ANNULLAMENTO")
        if replay is not None:      # richiesta identica conclusa mentre attendevo il lock
            return replay
        if not row or row[1] != "PAGAMENTO":
            raise PagamentoConsegnaOriginaleNonTrovatoError(
                f"{command.pagamento_id.value} non e' un pagamento consegna registrato."
            )
        original_pk, _, consegna_pk, consegna_public = row
        cursor.execute(
            "SELECT public_id FROM tpo.pagamenti_consegna WHERE annulla_pagamento_id=%s",
            (original_pk,),
        )
        done = cursor.fetchone()
        if done:
            raise PagamentoConsegnaGiaAnnullatoError(
                f"{command.pagamento_id.value} e' gia' annullato ({done[0]})."
            )
        public_id, sequence = self._allocate(cursor)
        authority = command.authority
        cursor.execute(
            """INSERT INTO tpo.pagamenti_consegna
               (public_id,consegna_id,tipo,annulla_pagamento_id,note,storico,
                idempotency_key,payload_hash,reason,correlation_id,created_by)
               VALUES (%s,%s,'ANNULLAMENTO',%s,%s,false,%s,%s,%s,%s,%s)
               RETURNING created_at""",
            (public_id.value, consegna_pk, original_pk, command.note,
             authority.idempotency_key, command.canonical_payload_hash, authority.reason,
             authority.correlation_id, authority.actor.value),
        )
        recorded_at = cursor.fetchone()[0]
        before = {"pagamento": command.pagamento_id.value, "consegna": consegna_public}
        after = {"public_id": public_id.value, "annulla": command.pagamento_id.value,
                 "consegna": consegna_public, "note": command.note,
                 "recorded_at": recorded_at.isoformat()}
        self._audit(cursor, recorded_at, authority, public_id.value, "CORRECTION", before,
                    after, "pagamento-consegna-annulla-v1")
        self._bump(cursor, sequence, recorded_at, authority.actor.value)
        return AnnullaPagamentoConsegnaResult(
            public_id, command.pagamento_id, ConsegnaId(consegna_public), recorded_at,
            "INSERTED",
        )

    # ------------------------------------------------------------------- common
    def _run(self, command, operation):
        for attempt in (1, 2):
            connection = self._factory.connect()
            cursor = None
            committed = False
            try:
                cursor = connection.cursor()
                result = operation(cursor, command)
                if getattr(result, "outcome", None) == "COMPATIBLE_REPLAY":
                    connection.rollback()
                    return result
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                try:
                    connection.commit()
                except Exception as exc:
                    raise PagamentoConsegnaCommitOutcomeUncertainError(
                        "Esito commit PAGAMENTO CONSEGNA da riconciliare."
                    ) from exc
                committed = True
                return result
            except psycopg.IntegrityError as exc:
                name = getattr(exc.diag, "constraint_name", "") or ""
                if name == _IDEMPOTENCY_CONSTRAINT and attempt == 1:
                    continue        # richiesta concorrente identica: la rilettura la riconosce
                raise self._integrity_error(exc) from exc
            except psycopg.Error as exc:
                message = str(exc)
                if "ct_pagamenti_consegna_coerente" in message:
                    raise PagamentoConsegnaPersistenceInvariantError(
                        "Vincolo PAGAMENTO CONSEGNA non soddisfatto."
                    ) from exc
                raise PagamentoConsegnaCommitRolledBackError(
                    "Registrazione PAGAMENTO CONSEGNA fallita con rollback certo."
                ) from exc
            finally:
                if not committed:
                    try: connection.rollback()
                    except Exception: pass
                if cursor is not None:
                    try: cursor.close()
                    except Exception: pass
                try: connection.close()
                except Exception: pass
        raise PagamentoConsegnaReconciliationRequiredError("Collisione idempotency da riconciliare.")

    @staticmethod
    def _replay(cursor: Any, key: str, payload_hash: str, tipo: str):
        cursor.execute(
            """SELECT p.payload_hash,p.tipo,p.public_id,c.public_id,p.data_pagamento,p.metodo,
                      p.importo,p.storico,p.created_at,orig.public_id
               FROM tpo.pagamenti_consegna p
               JOIN tpo.consegne c ON c.id=p.consegna_id
               LEFT JOIN tpo.pagamenti_consegna orig ON orig.id=p.annulla_pagamento_id
               WHERE p.idempotency_key=%s""",
            (key,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        if row[0] != payload_hash or row[1] != tipo:
            raise PagamentoConsegnaIdempotencyConflictError(
                "Stessa idempotency key PAGAMENTO CONSEGNA con payload differente."
            )
        try:
            if tipo == "PAGAMENTO":
                return RegistraPagamentoConsegnaResult(
                    PagamentoConsegnaId(row[2]), ConsegnaId(row[3]), row[4],
                    MetodoPagamento(row[5]), None if row[6] is None else Decimal(row[6]),
                    bool(row[7]), row[8], "COMPATIBLE_REPLAY",
                )
            return AnnullaPagamentoConsegnaResult(
                PagamentoConsegnaId(row[2]), PagamentoConsegnaId(row[9]), ConsegnaId(row[3]),
                row[8], "COMPATIBLE_REPLAY",
            )
        except Exception as exc:
            raise PagamentoConsegnaPersistenceInvariantError(
                "Risultato PAGAMENTO CONSEGNA persistito invalido."
            ) from exc

    @staticmethod
    def _lock_consegna(cursor: Any, consegna_id: ConsegnaId) -> int:
        cursor.execute(
            "SELECT id,stato::text FROM tpo.consegne WHERE public_id=%s FOR UPDATE",
            (consegna_id.value,),
        )
        row = cursor.fetchone()
        if not row:
            raise PagamentoConsegnaNonTrovataError(f"CONSEGNA {consegna_id.value} non trovata.")
        if row[1] != "CONSEGNATA":
            raise PagamentoConsegnaNonConsegnataError(
                f"{consegna_id.value} non e' CONSEGNATA: si registra il pagamento solo di "
                "consegne effettuate."
            )
        return row[0]

    @staticmethod
    def _allocate(cursor: Any):
        cursor.execute(
            """SELECT sequence_name,identifier_type,prefix,next_value,version
               FROM tpo.id_sequences WHERE sequence_name=%s FOR UPDATE""",
            (PagamentoConsegnaId.sequence_name,),
        )
        row = cursor.fetchone()
        if (not row or row[1] != PagamentoConsegnaId.__name__
                or row[2] != PagamentoConsegnaId.prefix):
            raise PagamentoConsegnaIdentityUnavailableError(
                "PAGAMENTO_CONSEGNA_ID assente o incompatibile."
            )
        try:
            return PagamentoConsegnaId(f"{row[2]}-{row[3]:06d}"), row
        except Exception as exc:
            raise PagamentoConsegnaIdentityUnavailableError(
                "PAGAMENTO_CONSEGNA_ID malformata."
            ) from exc

    @staticmethod
    def _bump(cursor: Any, sequence, recorded_at, actor: str) -> None:
        cursor.execute(
            """UPDATE tpo.id_sequences SET next_value=%s,version=version+1,
               updated_at=%s,updated_by=%s WHERE sequence_name=%s
               AND identifier_type=%s AND prefix=%s AND next_value=%s AND version=%s""",
            (sequence[3] + 1, recorded_at, actor, PagamentoConsegnaId.sequence_name,
             PagamentoConsegnaId.__name__, PagamentoConsegnaId.prefix, sequence[3], sequence[4]),
        )
        if cursor.rowcount != 1:
            raise PagamentoConsegnaIdentityUnavailableError(
                "Conflitto contatore PAGAMENTO_CONSEGNA_ID."
            )

    @staticmethod
    def _audit(cursor, recorded_at, authority, public_id, operation, before, after, boundary):
        cursor.execute(
            """INSERT INTO tpo.audit_eventi
               (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                before_data,after_data,correlation_id,provenance)
               VALUES (%s,%s,'PAGAMENTO_CONSEGNA',%s,%s,%s,%s,%s,%s,%s)""",
            (recorded_at, authority.actor.value, public_id, operation, authority.reason,
             None if before is None else Jsonb(before), Jsonb(after), authority.correlation_id,
             json.dumps({"boundary": boundary, "idempotency_key": authority.idempotency_key},
                        sort_keys=True)),
        )

    @staticmethod
    def _integrity_error(exc: psycopg.IntegrityError) -> Exception:
        name = getattr(exc.diag, "constraint_name", "") or ""
        if name == _IDEMPOTENCY_CONSTRAINT:
            return PagamentoConsegnaReconciliationRequiredError(
                "Collisione idempotency da riconciliare."
            )
        if name in {"pagamenti_consegna_public_id_key", "ck_pagamenti_consegna_public_id_format"}:
            return PagamentoConsegnaIdentityUnavailableError("Collisione PGC identity.")
        if name == "uq_pagamenti_consegna_annulla":
            return PagamentoConsegnaGiaAnnullatoError("Pagamento gia' annullato.")
        if name.startswith("ck_pagamenti_consegna_") or name.startswith("fk_pagamenti_consegna_"):
            return PagamentoConsegnaPersistenceInvariantError(
                "Vincolo PAGAMENTO CONSEGNA non soddisfatto."
            )
        return PagamentoConsegnaCommitRolledBackError("Vincolo PAGAMENTO CONSEGNA non soddisfatto.")
