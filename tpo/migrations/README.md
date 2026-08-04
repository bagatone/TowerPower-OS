# PostgreSQL migrations

Le migrazioni Alembic definiscono in modo incrementale lo schema fisico `tpo`.
Devono essere eseguite esplicitamente dal runtime con impostazioni PostgreSQL
validate; importare il package non apre connessioni e non applica migrazioni.

La prima revisione contiene soltanto le fondamenta runtime autorizzate:
`id_sequences`, `runs`, `run_messaggi` e `run_log`.

## Policy di downgrade dello schema

Il downgrade della revisione iniziale rimuove soltanto gli oggetti creati e
governati dalla catena Alembic. Lo schema `tpo` viene eliminato, senza
`CASCADE`, soltanto dopo la rimozione delle tabelle e degli enum appartenenti
alla revisione.

Se nello schema sono presenti oggetti estranei o non governati, il downgrade
deve fallire anziché eliminarli implicitamente. Questo comportamento è
intenzionale e protegge dalla perdita di dati. Nessun oggetto deve essere
creato manualmente nello schema `tpo`: ogni ambiente deve poter essere
ricostruito esclusivamente tramite migrazioni versionate.
