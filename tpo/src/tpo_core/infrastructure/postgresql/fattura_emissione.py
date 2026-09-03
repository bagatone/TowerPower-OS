"""Atomic PostgreSQL writer for Fattura Emissione V1.

Autorità: docs/architecture/FATTURA_AUTHORITY_FREEZE.md (Owner Decisions D1-D7).
Numerazione: allocata nella stessa transazione dell'INSERT su tpo.fatture
tramite compare-and-set su tpo.fattura_numerazione (Owner Decision D2) -
questo e' il meccanismo che garantisce "senza buchi" per la serie legale,
a differenza di tpo.id_sequences (che tollera gap tra transazioni separate).
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.fattura_emissione.errors import (
    FatturaCommitError,
    FatturaCommitOutcomeUncertain,
    FatturaConcurrencyError,
    FatturaIdempotencyConflictError,
    FatturaReconciliationRequiredError,
    FatturaValidationError,
    InvalidEmitFatturaCommandError,
)
from ...application.fattura_emissione.models import EmitFattura, EmitFatturaResult
from ...domain.identifiers import NumeroFattura
from .connection import PostgreSQLConnectionFactory

SCOPE = "FATTURA_EMISSIONE_V1"
TWO_PLACES = Decimal("0.01")


class PostgreSQLFatturaEmissioneWriter:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def emit(self, command: EmitFattura) -> EmitFatturaResult:
        if not isinstance(command, EmitFattura):
            raise InvalidEmitFatturaCommandError("command non valido.")
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
                raise FatturaReconciliationRequiredError(
                    "Reservation idempotency non riconciliabile."
                )
            result = self._execute(cursor, command, reservation_id)
            try:
                connection.commit()
            except Exception as exc:
                raise FatturaCommitOutcomeUncertain(
                    "Esito del commit FATTURA_EMISSIONE da riconciliare tramite idempotency_key."
                ) from exc
            committed = True
            return result
        except (FatturaValidationError, FatturaConcurrencyError,
                FatturaIdempotencyConflictError, FatturaReconciliationRequiredError,
                FatturaCommitOutcomeUncertain):
            raise
        except psycopg.IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        except (psycopg.errors.SerializationFailure, psycopg.errors.DeadlockDetected) as exc:
            raise FatturaConcurrencyError("Conflitto concorrente FATTURA_EMISSIONE.") from exc
        except psycopg.Error as exc:
            raise FatturaCommitError("FATTURA_EMISSIONE non completata con rollback certo.") from exc
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
        cursor: Any, command: EmitFattura,
    ) -> tuple[int | None, EmitFatturaResult | None]:
        cursor.execute(
            """INSERT INTO tpo.fattura_emissione_requests
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
        return None, PostgreSQLFatturaEmissioneWriter._replay(cursor, command)

    @staticmethod
    def _replay(cursor: Any, command: EmitFattura) -> EmitFatturaResult:
        cursor.execute(
            """SELECT r.canonical_payload_hash, r.outcome, f.id, f.numero_fattura,
                      f.data_emissione, f.scadenza, f.totale_netto, f.totale_igic,
                      f.totale, r.recorded_at,
                      (SELECT count(*) FROM tpo.fatture_consegne fc WHERE fc.fattura_id=f.id),
                      (SELECT count(*) FROM tpo.righe_fattura rf WHERE rf.fattura_id=f.id)
               FROM tpo.fattura_emissione_requests r
               LEFT JOIN tpo.fatture f ON f.id=r.fattura_id
               WHERE r.operation_scope=%s AND r.idempotency_key=%s
               FOR UPDATE OF r""",
            (SCOPE, command.authority.idempotency_key),
        )
        row = cursor.fetchone()
        if row is None:
            raise FatturaReconciliationRequiredError(
                "Reservation idempotency concorrente non leggibile."
            )
        if row[0] != command.canonical_payload_hash:
            raise FatturaIdempotencyConflictError(
                "Stessa idempotency key con payload differente."
            )
        if row[1] != "COMMITTED" or row[2] is None:
            raise FatturaReconciliationRequiredError(
                "Reservation idempotency priva di risultato committed."
            )
        return EmitFatturaResult(
            fattura_id=row[2], outcome="COMPATIBLE_REPLAY", numero_fattura=NumeroFattura(row[3]),
            cliente_id=command.cliente_id, data_emissione=row[4], scadenza=row[5],
            totale_netto=Decimal(row[6]), totale_igic=Decimal(row[7]), totale=Decimal(row[8]),
            consegna_count=row[10], riga_count=row[11], recorded_at=row[9],
        )

    @classmethod
    def _execute(cls, cursor: Any, command: EmitFattura, reservation_id: int) -> EmitFatturaResult:
        cliente_pk, termini_pagamento_giorni = cls._cliente(cursor, command.cliente_id)
        consegne = cls._consegne(cursor, command.consegna_ids, cliente_pk)
        righe = cls._righe_consegna(cursor, [pk for pk, _public_id in consegne])
        listino = cls._listino(cursor, righe)

        totale_netto = Decimal("0.00")
        totale_igic = Decimal("0.00")
        riga_payloads: list[dict[str, Any]] = []
        computed_righe: list[dict[str, Any]] = []
        posizione = 0
        for consegna_pk, _consegna_public_id in consegne:
            for riga_id, varieta_id, varieta_public_id, quantita, unita_misura in righe[consegna_pk]:
                posizione += 1
                prezzo_unitario, aliquota_igic = listino[varieta_id]
                importo_netto = (Decimal(quantita) * prezzo_unitario).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
                importo_igic = (importo_netto * aliquota_igic / Decimal(100)).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
                totale_netto += importo_netto
                totale_igic += importo_igic
                computed_righe.append({
                    "posizione": posizione, "riga_consegna_id": riga_id, "varieta_id": varieta_id,
                    "quantita": quantita, "unita_misura": unita_misura,
                    "prezzo_unitario": prezzo_unitario, "aliquota_igic": aliquota_igic,
                    "importo_netto": importo_netto, "importo_igic": importo_igic,
                })
                riga_payloads.append({
                    "posizione": posizione, "varieta_public_id": varieta_public_id,
                    "quantita": str(quantita), "unita_misura": unita_misura,
                    "prezzo_unitario": str(prezzo_unitario), "aliquota_igic": str(aliquota_igic),
                    "importo_netto": str(importo_netto), "importo_igic": str(importo_igic),
                })
        if not computed_righe:
            raise FatturaValidationError("Nessuna RIGA_CONSEGNA fatturabile nelle CONSEGNE indicate.")
        totale = totale_netto + totale_igic

        numero_fattura = cls._allocate_numero(cursor, command.data_emissione)
        scadenza = command.data_emissione + timedelta(days=termini_pagamento_giorni)

        cursor.execute(
            """INSERT INTO tpo.fatture
               (numero_fattura,cliente_id,data_emissione,scadenza,
                totale_netto,totale_igic,totale,rettifica_di,created_at,created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,NULL,CURRENT_TIMESTAMP,%s)
               RETURNING id,created_at""",
            (numero_fattura, cliente_pk, command.data_emissione, scadenza,
             totale_netto, totale_igic, totale, command.authority.actor.value),
        )
        fattura_pk, created_at = cursor.fetchone()

        for position, (consegna_pk, _public_id) in enumerate(consegne, 1):
            cursor.execute(
                "INSERT INTO tpo.fatture_consegne(fattura_id,consegna_id,posizione) VALUES (%s,%s,%s)",
                (fattura_pk, consegna_pk, position),
            )

        for entry in computed_righe:
            cursor.execute(
                """INSERT INTO tpo.righe_fattura
                   (fattura_id,riga_consegna_id,posizione,varieta_id,quantita,unita_misura,
                    prezzo_unitario,aliquota_igic,importo_netto,importo_igic,
                    created_at,created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,%s)""",
                (fattura_pk, entry["riga_consegna_id"], entry["posizione"], entry["varieta_id"],
                 entry["quantita"], entry["unita_misura"], entry["prezzo_unitario"],
                 entry["aliquota_igic"], entry["importo_netto"], entry["importo_igic"],
                 command.authority.actor.value),
            )

        cursor.execute(
            """UPDATE tpo.fattura_emissione_requests
               SET fattura_id=%s,outcome='COMMITTED',recorded_at=%s
               WHERE id=%s AND operation_scope=%s AND canonical_payload_hash=%s
                 AND outcome='RESERVED' AND fattura_id IS NULL""",
            (fattura_pk, created_at, reservation_id, SCOPE, command.canonical_payload_hash),
        )
        if cursor.rowcount != 1:
            raise FatturaConcurrencyError("Reservation idempotency non aggiornabile.")

        cls._audit(cursor, command, fattura_pk, numero_fattura, consegne, riga_payloads,
                   totale_netto, totale_igic, totale, created_at)

        return EmitFatturaResult(
            fattura_id=fattura_pk, outcome="INSERTED", numero_fattura=NumeroFattura(numero_fattura),
            cliente_id=command.cliente_id, data_emissione=command.data_emissione, scadenza=scadenza,
            totale_netto=totale_netto, totale_igic=totale_igic, totale=totale,
            consegna_count=len(consegne), riga_count=len(computed_righe), recorded_at=created_at,
        )

    @staticmethod
    def _cliente(cursor: Any, cliente_id: Any) -> tuple[int, int]:
        cursor.execute(
            "SELECT id,termini_pagamento_giorni FROM tpo.clienti WHERE public_id=%s FOR SHARE",
            (cliente_id.value,),
        )
        row = cursor.fetchone()
        if row is None:
            raise FatturaValidationError("CLIENTE assente.")
        if row[1] is None:
            raise FatturaValidationError(
                "CLIENTE non configurato per fatturazione: termini_pagamento_giorni assente."
            )
        return row[0], row[1]

    @staticmethod
    def _consegne(cursor: Any, consegna_ids: tuple[Any, ...], cliente_pk: int) -> list[tuple[int, str]]:
        public_ids = [item.value for item in consegna_ids]
        cursor.execute(
            """SELECT id,public_id,cliente_id,stato FROM tpo.consegne
               WHERE public_id = ANY(%s) ORDER BY id FOR UPDATE""",
            (public_ids,),
        )
        rows = cursor.fetchall()
        if len(rows) != len(public_ids):
            raise FatturaValidationError("Una o più CONSEGNE non esistono.")
        by_public = {row[1]: row for row in rows}
        for public_id in public_ids:
            row = by_public[public_id]
            if row[3] != "CONSEGNATA":
                raise FatturaValidationError("Una CONSEGNA non CONSEGNATA non può essere fatturata.")
            if row[2] != cliente_pk:
                raise FatturaValidationError("Una CONSEGNA non appartiene al CLIENTE indicato.")
        cursor.execute(
            "SELECT consegna_id FROM tpo.fatture_consegne WHERE consegna_id = ANY(%s)",
            ([row[0] for row in rows],),
        )
        if cursor.fetchone() is not None:
            raise FatturaValidationError("Una o più CONSEGNE risultano già fatturate.")
        return [(by_public[public_id][0], public_id) for public_id in public_ids]

    @staticmethod
    def _righe_consegna(cursor: Any, consegna_pks: list[int]) -> dict[int, list[tuple[Any, ...]]]:
        cursor.execute(
            """SELECT rc.id,rc.consegna_id,rc.varieta_id,v.public_id,rc.quantita,rc.unita_misura,
                      rc.rettifica_riga_consegna_id
               FROM tpo.righe_consegna rc
               JOIN tpo.varieta v ON v.id=rc.varieta_id
               WHERE rc.consegna_id = ANY(%s)
               ORDER BY rc.consegna_id,rc.posizione FOR SHARE OF rc""",
            (consegna_pks,),
        )
        rows = cursor.fetchall()
        by_consegna: dict[int, list[tuple[Any, ...]]] = {pk: [] for pk in consegna_pks}
        for riga_id, consegna_pk, varieta_id, varieta_public_id, quantita, unita_misura, rettifica_di in rows:
            if rettifica_di is not None:
                raise FatturaValidationError(
                    "RIGA_CONSEGNA rettificativa non fatturabile in V1 (fuori scope)."
                )
            by_consegna[consegna_pk].append((riga_id, varieta_id, varieta_public_id, quantita, unita_misura))
        for pk, lines in by_consegna.items():
            if not lines:
                raise FatturaValidationError("Una CONSEGNA fatturabile non ha righe fatturabili.")
        return by_consegna

    @staticmethod
    def _listino(cursor: Any, righe: dict[int, list[tuple[Any, ...]]]) -> dict[int, tuple[Decimal, Decimal]]:
        varieta_ids = sorted({riga[1] for lines in righe.values() for riga in lines})
        cursor.execute(
            """SELECT varieta_id,prezzo_unitario,aliquota_igic FROM tpo.listino_varieta
               WHERE varieta_id = ANY(%s) FOR SHARE""",
            (varieta_ids,),
        )
        result = {row[0]: (Decimal(row[1]), Decimal(row[2])) for row in cursor.fetchall()}
        missing = set(varieta_ids) - set(result)
        if missing:
            raise FatturaValidationError("LISTINO_VARIETA mancante per una o più varietà da fatturare.")
        return result

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
            raise FatturaCommitError("fattura_numerazione non inizializzabile.")
        next_value, version = row
        cursor.execute(
            """UPDATE tpo.fattura_numerazione SET next_value=%s,version=%s
               WHERE anno=%s AND version=%s""",
            (next_value + 1, version + 1, anno, version),
        )
        if cursor.rowcount != 1:
            raise FatturaConcurrencyError("Numerazione FATTURA in conflitto concorrente.")
        return f"{anno:04d}/{next_value:04d}"

    @staticmethod
    def _audit(cursor: Any, command: EmitFattura, fattura_pk: int, numero_fattura: str,
               consegne: list[tuple[int, str]], riga_payloads: list[dict[str, Any]],
               totale_netto: Decimal, totale_igic: Decimal, totale: Decimal, recorded_at: Any) -> None:
        after = {
            "internal_id": fattura_pk,
            "numero_fattura": numero_fattura,
            "cliente_public_id": command.cliente_id.value,
            "data_emissione": command.data_emissione.isoformat(),
            "consegne_public_id": [public_id for _pk, public_id in consegne],
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
                after_data,correlation_id,provenance)
               VALUES (%s,%s,'FATTURA',%s,'INSERT',%s,%s,%s,%s)""",
            (recorded_at, command.authority.actor.value, numero_fattura,
             command.authority.reason, Jsonb(after), command.authority.correlation_id,
             json.dumps({"boundary": "fattura-emissione-v1"}, sort_keys=True)),
        )

    @staticmethod
    def _integrity_error(exc: psycopg.IntegrityError) -> Exception:
        name = getattr(exc.diag, "constraint_name", "")
        if name == "uq_fattura_emissione_request_key":
            return FatturaReconciliationRequiredError("Collisione idempotency inattesa da riconciliare.")
        if name == "fatture_numero_fattura_key":
            return FatturaConcurrencyError("Numerazione FATTURA in conflitto concorrente.")
        if name == "uq_fatture_consegne_consegna":
            return FatturaValidationError("Una CONSEGNA risulta già fatturata.")
        if name == "uq_righe_fattura_riga_consegna":
            return FatturaValidationError("Una RIGA_CONSEGNA risulta già fatturata.")
        return FatturaCommitError("Vincolo FATTURA_EMISSIONE non soddisfatto.")
