# Note operative

## Cosa fa questa prima versione

- Legge da GitHub i documenti operativi richiesti.
- Salva una copia cache dei documenti in `data/cache/`.
- Legge in sola lettura i fogli Google Sheets configurati.
- Valida le intestazioni usando `TPO_SHEETS_SCHEMA.md`.
- Calcola gli allarmi stock.
- Produce il report `AGGIORNAMI` con allarmi, stock, consegne, lotti, semine, problemi e azioni operative.

## Cosa non fa ancora

- Non scrive nei fogli.
- Non modifica righe esistenti.
- Non crea nuovi record su Google Sheets.
- Non invia notifiche esterne.

## File Python principali

- `src/github_loader.py`: scarica i Markdown dal repository GitHub.
- `src/sheets_loader.py`: legge i fogli Google Sheets.
- `src/schema_validator.py`: valida le intestazioni rispetto allo schema Markdown.
- `src/stock_alarm.py`: genera allarmi quando `DISPONIBILE < PRENOTATO`.
- `src/row_generator.py`: prepara azioni operative in memoria, senza scrittura.
- `src/aggiornami.py`: orchestra il comando `AGGIORNAMI`.
