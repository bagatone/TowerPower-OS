"""Consumo di lotto condiviso (CONSUMO_LOTTO, vedi
docs/architecture/CONSUMO_LOTTO_AUTHORITY_FREEZE.md).

Spiega, per un MOVIMENTO SCARICO appena scritto, da quali MOVIMENTI CARICO
(ingressi da RACCOLTA, dunque da quale SEMINA e codice ``AAA-GGMM-L``) proviene
la quantita' uscita, senza fondere i codici di origine. Usato dal Delivery
Fulfilment (``tipo_consumo='CONSEGNA'``) e dalla rettifica di giacenza
(``tipo_consumo='RETTIFICA_GIACENZA'``).

Unita' di tracciabilita' (migrazione 20261003_0037): un CARICO con RACCOLTA e'
misurato nell'unita' e nella quantita' della RACCOLTA (SET), anche se il
MOVIMENTO e' in GRAM (carichi storici di Afila/Cilantro); un CARICO senza
RACCOLTA nella propria unita'.

Due modalita':

- automatica (FIFO per data di carico): non bloccante. Se la provenienza
  tracciabile disponibile non basta a spiegare l'intera quantita' (giacenza
  precedente al ledger), l'operazione procede e la parte non spiegata resta
  senza lotto di origine: non viene mai inventata. La giacenza senza origine
  (D5) e' la piu' vecchia e si consuma per prima.
- dichiarata (``origin_semina``): si consumano ESCLUSIVAMENTE i lotti della
  SEMINA indicata, oppure l'operazione viene rifiutata via ``fail``: un codice
  dichiarato che il sistema non puo' onorare non viene mai sostituito.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any


def consume_lots(
    cursor: Any, *, varieta_pk: int, unit: str, movimento_scarico_id: int,
    quantity_needed: Decimal, persistence_at: datetime, actor: str,
    tipo_consumo: str, origin_semina: str | None,
    fail: Callable[[str], Exception],
) -> None:
    if origin_semina is not None:
        _consume_declared(
            cursor, varieta_pk, unit, movimento_scarico_id, quantity_needed,
            persistence_at, actor, tipo_consumo, origin_semina, fail,
        )
        return
    cursor.execute(
        """SELECT m.id,
                  COALESCE(r.quantita, m.quantita) - COALESCE(consumato.totale, 0) AS residuo
           FROM tpo.movimenti_magazzino m
           LEFT JOIN tpo.raccolte r ON r.id = m.raccolta_id
           LEFT JOIN (
               SELECT movimento_carico_id, SUM(quantita) AS totale
               FROM tpo.consumi_lotto GROUP BY movimento_carico_id
           ) consumato ON consumato.movimento_carico_id = m.id
           WHERE m.varieta_id = %s AND m.tipo = 'CARICO'
             AND COALESCE(r.unita_misura, m.unita_misura)::text = %s
           ORDER BY m.data_movimento ASC, m.id ASC
           FOR UPDATE OF m""",
        (varieta_pk, unit),
    )
    carichi = cursor.fetchall()
    # Giacenza SENZA origine tracciabile (D5): lo STOCK gia' presente quando e'
    # nato il ledger non ha alcun MOVIMENTO CARICO. E' piu' vecchia di qualsiasi
    # CARICO futuro, quindi in FIFO si consuma per prima e NON viene attribuita a
    # nessun codice. Calcolata a runtime come: giacenza prima di questo scarico
    # - residuo di tutti i CARICO.
    cursor.execute(
        "SELECT disponibile FROM tpo.stock WHERE varieta_id=%s AND unita_misura=%s",
        (varieta_pk, unit),
    )
    stock_row = cursor.fetchone()
    remaining = quantity_needed
    if stock_row is not None:
        traced_residual = sum(
            (Decimal(r) for _, r in carichi if r is not None and r > 0), Decimal(0)
        )
        untraced = Decimal(stock_row[0]) + quantity_needed - traced_residual
        if untraced > 0:
            remaining -= min(untraced, remaining)
    for carico_id, residuo in carichi:
        if remaining <= 0:
            break
        if residuo is None or residuo <= 0:
            continue
        take = Decimal(residuo) if Decimal(residuo) < remaining else remaining
        _insert(cursor, carico_id, movimento_scarico_id, tipo_consumo, take,
                persistence_at, actor)
        remaining -= take


def _consume_declared(
    cursor: Any, varieta_pk: int, unit: str, movimento_scarico_id: int,
    quantity_needed: Decimal, persistence_at: datetime, actor: str,
    tipo_consumo: str, origin_semina: str, fail: Callable[[str], Exception],
) -> None:
    cursor.execute(
        "SELECT id, varieta_id FROM tpo.semine WHERE public_id=%s", (origin_semina,),
    )
    semina = cursor.fetchone()
    if semina is None:
        raise fail(f"SEMINA dichiarata {origin_semina} inesistente.")
    if semina[1] != varieta_pk:
        raise fail(f"SEMINA dichiarata {origin_semina} appartiene a un'altra VARIETA.")
    cursor.execute(
        """SELECT m.id,
                  COALESCE(r.quantita, m.quantita) - COALESCE(consumato.totale, 0) AS residuo
           FROM tpo.movimenti_magazzino m
           JOIN tpo.raccolte r ON r.id = m.raccolta_id
           LEFT JOIN (
               SELECT movimento_carico_id, SUM(quantita) AS totale
               FROM tpo.consumi_lotto GROUP BY movimento_carico_id
           ) consumato ON consumato.movimento_carico_id = m.id
           WHERE m.varieta_id = %s AND m.tipo = 'CARICO' AND r.semina_id = %s
             AND r.unita_misura::text = %s
           ORDER BY m.data_movimento ASC, m.id ASC
           FOR UPDATE OF m""",
        (varieta_pk, semina[0], unit),
    )
    carichi = [(c, r) for c, r in cursor.fetchall() if r is not None and r > 0]
    available = sum((Decimal(r) for _, r in carichi), Decimal(0))
    if available < quantity_needed:
        raise fail(
            f"SEMINA dichiarata {origin_semina}: disponibile in magazzino "
            f"{available} {unit}, richiesto {quantity_needed} {unit}."
        )
    remaining = quantity_needed
    for carico_id, residuo in carichi:
        if remaining <= 0:
            break
        take = Decimal(residuo) if Decimal(residuo) < remaining else remaining
        _insert(cursor, carico_id, movimento_scarico_id, tipo_consumo, take,
                persistence_at, actor)
        remaining -= take


def _insert(cursor: Any, carico_id: int, scarico_id: int, tipo_consumo: str,
            quantity: Decimal, persistence_at: datetime, actor: str) -> None:
    cursor.execute(
        """INSERT INTO tpo.consumi_lotto
           (movimento_carico_id, movimento_scarico_id, tipo_consumo,
            quantita, created_at, created_by)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (carico_id, scarico_id, tipo_consumo, quantity, persistence_at, actor),
    )
