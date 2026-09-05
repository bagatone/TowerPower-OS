"""Atomic PostgreSQL writer for Fattura Rettifica V1 (RectifyFattura).

Autorità: docs/architecture/RECTIFY_FATTURA_AUTHORITY_FREEZE.md. Implementa
la riserva di FATTURA_AUTHORITY_FREEZE.md §16 (Owner Decision D7): una
rettifica è una nuova FATTURA con proprio numero_fattura (stessa serie
annuale/compare-and-set su tpo.fattura_numerazione di EmitFattura), che
corregge una o più righe specifiche della fattura originale (Owner Decision
D8). prezzo_unitario/aliquota_igic/varieta_id sono copiati dalla riga
originale, mai ri-letti da LISTINO_VARIETA (Sezione 4 del freeze).
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.fattura_rettifica.errors import (
    FatturaRettificaCommitError,
    FatturaRettificaCommitOutcomeUncertain,
    FatturaRettificaConcurrencyError,
    FatturaRettificaIdempotencyConflictError,
    FatturaRettificaReconciliationRequiredError,
    FatturaRettificaValidationError,
    InvalidRectifyFatturaCommandError,
)
from ...application.fattura_rettifica.models import RectifyFattura, RectifyFatturaResult
from ...domain.identifiers import ClienteId, NumeroFattura
from .connection import PostgreSQLConnectionFactory

SCOPE = "FATTURA_RETTIFICA_V1"
TWO_PLACES = Decimal("0.01")


class PostgreSQLFatturaRettificaWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def rectify(self, command: RectifyFattura) -> RectifyFatturaResult:
        if not isinstance(command, RectifyFattura):
            raise InvalidRectifyFatturaCommandError("command non valido.")
        connection = self._factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            reservation_id, replay = self._reserve_or_replay(cursor, command)
            if replay is not None:
                connection.rollback()
                return replay
            if reservation_id is None:
                raise FatturaRettificaReconciliationRequiredError(
                    "Reservation idempotency non riconciliabile."
                )
            result = self._execute(cursor, command, reservation_id)
            try:
                connection.commit()
            except Exception as exc:
                raise FatturaRettificaCommitOutcomeUncertain(
                    "Esito del commit FATTURA_RETTIFICA da riconciliare tramite idempotency_key."
                ) from exc
            committed = True
            return result
        except (FatturaRettificaValidationError, FatturaRettificaConcurrencyError,
                FatturaRettificaIdempotencyConflictError, FatturaRettificaReconciliationRequiredError,
                FatturaRettificaCommitOutcomeUncertain):
            raise
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except (psycopg.errors.SerializationFailure, psycopg.errors.DeadlockDetected) as exc:
            raise FatturaRettificaConcurrencyError("Conflitto concorrente FATTURA_RETTIFICA.") from exc
        except psycopg.Error as exc:
            raise FatturaRettificaCommitError(
                "FATTURA_RETTIFICA non completata con rollback certo."
            ) from exc
        finally:
            if not committed:
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

    @staticmethod
    def _reserve_or_replay(
        cursor: Any, command: RectifyFattura,
    ) -> tuple[int | None, RectifyFatturaResult | None]:
        cursor.execute(
            """INSERT INTO tpo.fattura_rettifica_requests
               (operation_scope,idempotency_key,canonical_payload_hash,
                fattura_id,outcome,recorded_at,created_by)
               VALUES (%s,%s,%s,NULL,'RESERVED',CURRENT_TIMESTAMP,%s)
               ON CONFLICT (operation_scope,idempotency_key) DO NOTHING
               RETURNING id""",
            (SCOPE, command.authority.idempotency_key,
             command.canonical_payload_hash, command.authority.actor.value),
        )
        row = cursor.fetchone()
        if row is not None:
            return row[0], None
        return None, PostgreSQLFatturaRettificaWriter._replay(cursor, command)

    @staticmethod
    def _replay(cursor: Any, command: RectifyFattura) -> RectifyFatturaResult:
        cursor.execute(
            """SELECT r.canonical_payload_hash, r.outcome, f.id, f.numero_fattura,
                      f.rettifica_di, c.public_id, f.data_emissione, f.scadenza,
                      f.totale_netto, f.totale_igic, f.totale, r.recorded_at,
                      (SELECT count(*) FROM tpo.righe_fattura rf WHERE rf.fattura_id=f.id)
               FROM tpo.fattura_rettifica_requests r
               LEFT JOIN tpo.fatture f ON f.id=r.fattura_id
               LEFT JOIN tpo.clienti c ON c.id=f.cliente_id
               WHERE r.operation_scope=%s AND r.idempotency_key=%s
               FOR UPDATE OF r""",
            (SCOPE, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if row is None:
            raise FatturaRettificaReconciliationRequiredError(
                "Reservation idempotency concorrente non leggibile."
            )
        if row[0] != command.canonical_payload_hash:
            raise FatturaRettificaIdempotencyConflictError(
                "Stessa idempotency key con payload differente."
            )
        if row[1] != "COMMITTED" or row[2] is None:
            raise FatturaRettificaReconciliationRequiredError(
                "Reservation idempotency priva di risultato committed."
            )
        return RectifyFatturaResult(
            fattura_id=row[2], outcome="COMPATIBLE_REPLAY", numero_fattura=NumeroFattura(row[3]),
            rettifica_di=NumeroFattura(row[4]), cliente_id=ClienteId(row[5]),
            data_emissione=row[6], scadenza=row[7], totale_netto=Decimal(row[8]),
            totale_igic=Decimal(row[9]), totale=Decimal(row[10]), riga_count=row[12],
            recorded_at=row[11],
        )

    @classmethod
    def _execute(cls, cursor: Any, command: RectifyFattura, reservation_id: int) -> RectifyFatturaResult:
        original_fattura_pk, cliente_pk, cliente_public_id, termini_pagamento_giorni, \
            original_rettifica_di = cls._original_fattura(cursor, command.rettifica_di)
        if original_rettifica_di is not None:
            raise FatturaRettificaValidationError(
                "La fattura originale è essa stessa una rettifica; niente "
                "rettifica-di-rettifica concatenata."
            )

        totale_netto = Decimal("0.00")
        totale_igic = Decimal("0.00")
        riga_payloads: list[dict[str, Any]] = []
        computed_righe: list[dict[str, Any]] = []
        posizione = 0
        for riga in command.righe:
            posizione += 1
            original = cls._original_riga(cursor, original_fattura_pk, riga.posizione_originale)
            importo_netto = (riga.quantita * original["prezzo_unitario"]).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )
            importo_igic = (importo_netto * original["aliquota_igic"] / Decimal(100)).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )
            totale_netto += importo_netto
            totale_igic += importo_igic
            computed_righe.append({
                "posizione": posizione, "rettifica_riga_fattura_id": original["id"],
                "varieta_id": original["varieta_id"], "quantita": riga.quantita,
                "unita_misura": original["unita_misura"],
                "prezzo_unitario": original["prezzo_unitario"],
                "aliquota_igic": original["aliquota_igic"],
                "importo_netto": importo_netto, "importo_igic": importo_igic,
            })
            riga_payloads.append({
                "posizione": posizione, "posizione_originale": riga.posizione_originale,
                "varieta_public_id": original["varieta_public_id"], "quantita": str(riga.quantita),
                "unita_misura": original["unita_misura"],
                "prezzo_unitario": str(original["prezzo_unitario"]),
                "aliquota_igic": str(original["aliquota_igic"]),
                "importo_netto": str(importo_netto), "importo_igic": str(importo_igic),
            })
        totale = totale_netto + totale_igic

        numero_fattura = cls._allocate_numero(cursor, command.data_emissione)
        scadenza = command.data_emissione + timedelta(days=termini_pagamento_giorni)

        cursor.execute(
            """INSERT INTO tpo.fatture
               (numero_fattura,cliente_id,data_emissione,scadenza,
                totale_netto,totale_igic,totale,rettifica_di,created_at,created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,%s)
               RETURNING id,created_at""",
            (numero_fattura, cliente_pk, command.data_emissione, scadenza,
             totale_netto, totale_igic, totale, command.rettifica_di.value,
             command.authority.actor.value),
        )
        fattura_pk, created_at = cursor.fetchone()

        for entry in computed_righe:
            cursor.execute(
                """INSERT INTO tpo.righe_fattura
                   (fattura_id,riga_consegna_id,posizione,varieta_id,quantita,unita_misura,
                    prezzo_unitario,aliquota_igic,importo_netto,importo_igic,
                    rettifica_riga_fattura_id,created_at,created_by)
                   VALUES (%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,%s)""",
                (fattura_pk, entry["posizione"], entry["varieta_id"], entry["quantita"],
                 entry["unita_misura"], entry["prezzo_unitario"], entry["aliquota_igic"],
                 entry["importo_netto"], entry["importo_igic"],
                 entry["rettifica_riga_fattura_id"], command.authority.actor.value),
            )

        cursor.execute(
            """UPDATE tpo.fattura_rettifica_requests
               SET fattura_id=%s,outcome='COMMITTED',recorded_at=%s
               WHERE id=%s AND operation_scope=%s AND canonical_payload_hash=%s
                 AND outcome='RESERVED' AND fattura_id IS NULL""",
            (fattura_pk, created_at, reservation_id, SCOPE, command.canonical_payload_hash),
        )
        if cursor.rowcount != 1:
            raise FatturaRettificaConcurrencyError("Reservation idempotency non aggiornabile.")

        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

        cls._audit(cursor, command, fattura_pk, numero_fattura, riga_payloads,
                   totale_netto, totale_igic, totale, created_at)

        return RectifyFatturaResult(
            fattura_id=fattura_pk, outcome="INSERTED", numero_fattura=NumeroFattura(numero_fattura),
            rettifica_di=command.rettifica_di, cliente_id=ClienteId(cliente_public_id),
            data_emissione=command.data_emissione, scadenza=scadenza,
            totale_netto=totale_netto, totale_igic=totale_igic, totale=totale,
            riga_count=len(computed_righe), recorded_at=created_at,
        )

    @staticmethod
    def _original_fattura(cursor: Any, numero_fattura: NumeroFattura) -> tuple[int, int, str, int, str | None]:
        cursor.execute(
            """SELECT f.id,f.cliente_id,c.public_id,c.termini_pagamento_giorni,f.rettifica_di
               FROM tpo.fatture f JOIN tpo.clienti c ON c.id=f.cliente_id
               WHERE f.numero_fattura=%s FOR SHARE OF f""",
            (numero_fattura.value,),
        )
        row = cursor.fetchone()
        if row is None:
            raise FatturaRettificaValidationError("FATTURA originale (rettifica_di) inesistente.")
        if row[3] is None:
            raise FatturaRettificaValidationError(
                "CLIENTE non configurato per fatturazione: termini_pagamento_giorni assente."
            )
        return row[0], row[1], row[2], row[3], row[4]

    @staticmethod
    def _original_riga(cursor: Any, fattura_pk: int, posizione: int) -> dict[str, Any]:
        cursor.execute(
            """SELECT rf.id,rf.varieta_id,v.public_id,rf.prezzo_unitario,rf.aliquota_igic,
                      rf.unita_misura,rf.rettifica_riga_fattura_id
               FROM tpo.righe_fattura rf JOIN tpo.varieta v ON v.id=rf.varieta_id
               WHERE rf.fattura_id=%s AND rf.posizione=%s FOR UPDATE OF rf""",
            (fattura_pk, posizione),
        )
        row = cursor.fetchone()
        if row is None:
            raise FatturaRettificaValidationError(
                f"Nessuna RIGA_FATTURA alla posizione {posizione} nella fattura originale."
            )
        if row[6] is not None:
            raise FatturaRettificaValidationError(
                f"La riga alla posizione {posizione} è già stata rettificata."
            )
        cursor.execute(
            "SELECT 1 FROM tpo.righe_fattura WHERE rettifica_riga_fattura_id=%s",
            (row[0],),
        )
        if cursor.fetchone() is not None:
            raise FatturaRettificaValidationError(
                f"La riga alla posizione {posizione} è già stata rettificata."
            )
        return {
            "id": row[0], "varieta_id": row[1], "varieta_public_id": row[2],
            "prezzo_unitario": Decimal(row[3]), "aliquota_igic": Decimal(row[4]),
            "unita_misura": row[5],
        }

    @staticmethod
    def _allocate_numero(cursor: Any, data_emissione: Any) -> str:
        anno = data_emissione.year
        cursor.execute(
            "INSERT INTO tpo.fattura_numerazione(anno) VALUES (%s) ON CONFLICT (anno) DO NOTHING",
            (anno,),
        )
        cursor.execute(
            "SELECT next_value,version FROM tpo.fattura_numerazione WHERE anno=%s FOR UPDATE",
            (anno,),
        )
        row = cursor.fetchone()
        if row is None:
            raise FatturaRettificaCommitError("fattura_numerazione non inizializzabile.")
        next_value, version = row
        cursor.execute(
            """UPDATE tpo.fattura_numerazione SET next_value=%s,version=%s
               WHERE anno=%s AND version=%s""",
            (next_value + 1, version + 1, anno, version),
        )
        if cursor.rowcount != 1:
            raise FatturaRettificaConcurrencyError("Numerazione FATTURA in conflitto concorrente.")
        return f"{anno:04d}/{next_value:04d}"

    @staticmethod
    def _audit(cursor: Any, command: RectifyFattura, fattura_pk: int, numero_fattura: str,
               riga_payloads: list[dict[str, Any]], totale_netto: Decimal, totale_igic: Decimal,
               totale: Decimal, recorded_at: Any) -> None:
        before = {"rettifica_di": command.rettifica_di.value}
        after = {
            "internal_id": fattura_pk,
            "numero_fattura": numero_fattura,
            "rettifica_di": command.rettifica_di.value,
            "data_emissione": command.data_emissione.isoformat(),
            "righe": riga_payloads,
            "totale_netto": str(totale_netto),
            "totale_igic": str(totale_igic),
            "totale": str(totale),
            "idempotency_key": command.authority.idempotency_key,
            "canonical_payload_hash": command.canonical_payload_hash,
        }
        cursor.execute(
            """INSERT INTO tpo.audit_eventi
               (occurred_at,actor,entity_type,entity_public_id,operation,reason,
                before_data,after_data,correlation_id,provenance)
               VALUES (%s,%s,'FATTURA',%s,'CORRECTION',%s,%s,%s,%s,%s)""",
            (recorded_at, command.authority.actor.value, numero_fattura,
             command.authority.reason, Jsonb(before), Jsonb(after),
             command.authority.correlation_id,
             json.dumps({"boundary": "fattura-rettifica-v1"}, sort_keys=True)),
        )

    @staticmethod
    def _integrity_error(exc: psycopg.IntegrityError) -> Exception:
        name = getattr(exc.diag, "constraint_name", "") or ""
        if name == "uq_fattura_rettifica_request_key":
            return FatturaRettificaReconciliationRequiredError(
                "Collisione idempotency inattesa da riconciliare."
            )
        if name == "fatture_numero_fattura_key":
            return FatturaRettificaConcurrencyError("Numerazione FATTURA in conflitto concorrente.")
        if name in {"uq_righe_fattura_rettifica_riga_fattura", "ck_righe_fattura_ordinaria_o_rettifica"}:
            return FatturaRettificaValidationError("Riga fattura originale già rettificata o vincolo violato.")
        if name in {"ct_righe_fattura_rettifica_coerente", "ct_fatture_rettifica_cliente_coerente"}:
            return FatturaRettificaValidationError("Vincolo di coerenza rettifica FATTURA non soddisfatto.")
        return FatturaRettificaCommitError("Vincolo FATTURA_RETTIFICA non soddisfatto.")
