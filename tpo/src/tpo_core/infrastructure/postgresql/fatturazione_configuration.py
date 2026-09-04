"""Writer diretti di Configuration mutabile per FATTURA V1.

Autorità: docs/architecture/FATTURA_AUTHORITY_FREEZE.md, Owner Decisions D4/D5,
e docs/architecture/LISTINO_VARIETA_GOVERNANCE_FREEZE.md per LISTINO_VARIETA.

CLIENTE (fatturazione) resta Configuration mutabile senza governance: nessuna
idempotency key, nessun audit_eventi, un semplice UPDATE governato solo
dall'esistenza del CLIENTE e dai CHECK dello schema (invariato).

LISTINO_VARIETA e' invece Configuration mutabile *governata*: resta "valore
corrente" (non diventa un Register a Facts), ma ogni scrittura riuscita di
ImpostaPrezzoListinoVarieta produce un evento in tpo.audit_eventi (prezzo
prima/dopo, actor, reason, correlation_id) nella stessa transazione atomica
dell'UPSERT, cosi' che lo storico dei prezzi non vada perso.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.listino_varieta.errors import (
    ListinoVarietaPersistenceError, ListinoVarietaVarietaNotFoundError,
)
from ...application.listino_varieta.models import (
    ImpostaPrezzoListinoVarieta, ImpostaPrezzoListinoVarietaResult,
)
from .connection import PostgreSQLConnectionFactory


class FatturazioneConfigurationError(RuntimeError):
    """Errore base dei writer di Configuration fatturazione."""


class ClienteFatturazioneValidationError(FatturazioneConfigurationError):
    """Il CLIENTE indicato non esiste."""


class PostgreSQLListinoVarietaWriter:
    """Writer atomico di ImpostaPrezzoListinoVarieta: VARIETA -> UPSERT -> audit.

    Un'unica transazione: (1) verifica che la VARIETA pubblica esista,
    (2) legge il prezzo/aliquota attuali (se una riga esiste già, sotto
    lock), (3) UPSERT del nuovo valore corrente, (4) inserisce un evento
    di audit UPDATE in tpo.audit_eventi con before/after, (5) commit.
    Nessuna idempotency key/reservation: impostare due volte lo stesso
    prezzo produce due eventi di audit distinti con lo stesso before/after,
    non un conflitto (docs/architecture/LISTINO_VARIETA_GOVERNANCE_FREEZE.md).
    """

    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def imposta_prezzo(
        self, command: ImpostaPrezzoListinoVarieta
    ) -> ImpostaPrezzoListinoVarietaResult:
        connection = self._factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            varieta_public_id = command.varieta_id.value
            cursor.execute(
                "SELECT id FROM tpo.varieta WHERE public_id=%s FOR SHARE",
                (varieta_public_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise ListinoVarietaVarietaNotFoundError("VARIETA assente.")
            varieta_pk = row[0]

            cursor.execute(
                """SELECT prezzo_unitario,aliquota_igic FROM tpo.listino_varieta
                   WHERE varieta_id=%s FOR UPDATE""",
                (varieta_pk,),
            )
            existing = cursor.fetchone()
            inserted = existing is None
            before = (
                None if existing is None
                else {"prezzo_unitario": str(existing[0]), "aliquota_igic": str(existing[1])}
            )

            actor = command.authority.actor.value
            cursor.execute(
                """INSERT INTO tpo.listino_varieta
                   (varieta_id,prezzo_unitario,aliquota_igic,created_at,created_by,
                    updated_at,updated_by)
                   VALUES (%s,%s,%s,CURRENT_TIMESTAMP,%s,CURRENT_TIMESTAMP,%s)
                   ON CONFLICT (varieta_id) DO UPDATE SET
                     prezzo_unitario=EXCLUDED.prezzo_unitario,
                     aliquota_igic=EXCLUDED.aliquota_igic,
                     updated_at=CURRENT_TIMESTAMP,
                     updated_by=EXCLUDED.updated_by
                   RETURNING prezzo_unitario,aliquota_igic,updated_at""",
                (varieta_pk, command.prezzo_unitario, command.aliquota_igic, actor, actor),
            )
            persisted_prezzo, persisted_aliquota, recorded_at = cursor.fetchone()

            # before/after usano entrambi la rappresentazione persistita da PostgreSQL
            # (scala dello schema: NUMERIC(12,4)/NUMERIC(5,2)), non la scala grezza
            # fornita dal chiamante: cosi' prezzo "prima" e "dopo" sono sempre
            # confrontabili come stringhe nell'evento di audit.
            after = {
                "prezzo_unitario": str(persisted_prezzo),
                "aliquota_igic": str(persisted_aliquota),
            }
            cursor.execute(
                """INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                    before_data,after_data,correlation_id)
                   VALUES (%s,%s,'LISTINO_VARIETA',%s,'UPDATE',%s,%s,%s,%s)""",
                (recorded_at, actor, varieta_public_id, command.authority.reason,
                 Jsonb(before) if before is not None else None, Jsonb(after),
                 command.authority.correlation_id),
            )

            connection.commit()
            committed = True
            return ImpostaPrezzoListinoVarietaResult(
                varieta_public_id=varieta_public_id,
                prezzo_unitario=persisted_prezzo,
                aliquota_igic=persisted_aliquota,
                recorded_at=recorded_at,
                inserted=inserted,
                updated=not inserted,
            )
        except ListinoVarietaVarietaNotFoundError:
            raise
        except psycopg.IntegrityError as exc:
            raise ListinoVarietaPersistenceError("Vincolo LISTINO_VARIETA violato.") from exc
        except psycopg.Error as exc:
            raise ListinoVarietaPersistenceError("Scrittura LISTINO_VARIETA fallita.") from exc
        finally:
            _cleanup(cursor, connection, rollback=not committed)


class PostgreSQLClienteFatturazioneWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def set_fatturazione(
        self, *, cliente_public_id: str, modalita_fatturazione: str,
        termini_pagamento_giorni: int, actor: str,
    ) -> None:
        connection = self._factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            cursor.execute(
                """UPDATE tpo.clienti SET modalita_fatturazione=%s,termini_pagamento_giorni=%s
                   WHERE public_id=%s""",
                (modalita_fatturazione, termini_pagamento_giorni, cliente_public_id),
            )
            if cursor.rowcount != 1:
                raise ClienteFatturazioneValidationError("CLIENTE assente.")
            connection.commit()
            committed = True
        except ClienteFatturazioneValidationError:
            raise
        except psycopg.IntegrityError as exc:
            raise ClienteFatturazioneValidationError("Vincolo CLIENTE fatturazione violato.") from exc
        except psycopg.Error as exc:
            raise FatturazioneConfigurationError("Scrittura CLIENTE fatturazione fallita.") from exc
        finally:
            _cleanup(cursor, connection, rollback=not committed)


def _cleanup(cursor: Any, connection: Any, *, rollback: bool) -> None:
    if rollback:
        try:
            connection.rollback()
        except Exception:
            pass
    if cursor is not None:
        try:
            cursor.close()
        except Exception:
            pass
    try:
        connection.close()
    except Exception:
        pass
