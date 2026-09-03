"""Writer diretti di Configuration mutabile per FATTURA V1.

Autorità: docs/architecture/FATTURA_AUTHORITY_FREEZE.md, Owner Decisions D4/D5.
LISTINO_VARIETA e i campi di fatturazione di CLIENTE sono esplicitamente
Configuration mutabile in V1 (non Fact): nessuna idempotency key, nessun
audit_eventi, nessuna reservation - un semplice UPSERT/UPDATE governato solo
dall'esistenza del riferimento (VARIETA/CLIENTE) e dai CHECK dello schema.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import psycopg

from .connection import PostgreSQLConnectionFactory


class FatturazioneConfigurationError(RuntimeError):
    """Errore base dei writer di Configuration fatturazione."""


class ListinoVarietaValidationError(FatturazioneConfigurationError):
    """La VARIETA indicata non esiste."""


class ClienteFatturazioneValidationError(FatturazioneConfigurationError):
    """Il CLIENTE indicato non esiste."""


class PostgreSQLListinoVarietaWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def set_prezzo(
        self, *, varieta_public_id: str, prezzo_unitario: Decimal, aliquota_igic: Decimal,
        actor: str,
    ) -> None:
        connection = self._factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT id FROM tpo.varieta WHERE public_id=%s FOR SHARE", (varieta_public_id,)
            )
            row = cursor.fetchone()
            if row is None:
                raise ListinoVarietaValidationError("VARIETA assente.")
            varieta_pk = row[0]
            cursor.execute(
                """INSERT INTO tpo.listino_varieta
                   (varieta_id,prezzo_unitario,aliquota_igic,created_at,created_by,
                    updated_at,updated_by)
                   VALUES (%s,%s,%s,CURRENT_TIMESTAMP,%s,CURRENT_TIMESTAMP,%s)
                   ON CONFLICT (varieta_id) DO UPDATE SET
                     prezzo_unitario=EXCLUDED.prezzo_unitario,
                     aliquota_igic=EXCLUDED.aliquota_igic,
                     updated_at=CURRENT_TIMESTAMP,
                     updated_by=EXCLUDED.updated_by""",
                (varieta_pk, prezzo_unitario, aliquota_igic, actor, actor),
            )
            connection.commit()
            committed = True
        except ListinoVarietaValidationError:
            raise
        except psycopg.IntegrityError as exc:
            raise ListinoVarietaValidationError("Vincolo LISTINO_VARIETA violato.") from exc
        except psycopg.Error as exc:
            raise FatturazioneConfigurationError("Scrittura LISTINO_VARIETA fallita.") from exc
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
