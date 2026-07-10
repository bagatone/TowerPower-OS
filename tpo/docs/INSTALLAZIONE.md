# Tower Power Operations - Bootstrap v2

Sistema Python in sola lettura per caricare documenti operativi, leggere Google Sheets, validare intestazioni e produrre il comando `AGGIORNAMI`.

## Struttura progetto

```text
.
├── config/
│   ├── settings.example.yaml
│   └── settings.yaml
├── data/
│   └── cache/
├── docs/
│   ├── AGENTS.md
│   ├── OPERATING_RULES.md
│   ├── TPO_SHEETS_SCHEMA.md
│   ├── TPO_BOOTSTRAP.md
│   ├── INSTALLAZIONE.md
│   └── NOTE_OPERATIVE.md
├── src/
│   ├── aggiornami.py
│   ├── config_loader.py
│   ├── document_provider.py
│   ├── github_loader.py
│   ├── row_generator.py
│   ├── schema_validator.py
│   ├── sheets_loader.py
│   └── stock_alarm.py
├── tests/
│   └── test_document_provider.py
├── .env.example
└── requirements.txt
```

## Installazione

Prima installazione ufficiale:

```bash
cd tpo
./bootstrap.sh
```

Uso quotidiano:

```bash
cd tpo
source .venv/bin/activate
```

Uscita dal venv:

```bash
deactivate
```

Esecuzione test:

```bash
python -m pytest
```

Installazione manuale:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp config/settings.example.yaml config/settings.yaml
cp .env.example .env
```

## Modalità LOCAL

Usa questa modalità per sviluppo locale e bootstrap iniziale.

```yaml
dry_run: true
document_source: local
```

Con `document_source: local`, il sistema non contatta GitHub e legge direttamente:

- `docs/AGENTS.md`
- `docs/OPERATING_RULES.md`
- `docs/TPO_SHEETS_SCHEMA.md`
- `docs/TPO_BOOTSTRAP.md`

Se uno dei quattro documenti manca, il comando si interrompe con:

```text
Documento mancante:
NOMEFILE
```

## Modalità GITHUB

Usa questa modalità in produzione quando i documenti ufficiali devono arrivare dal repository.

```yaml
dry_run: true
document_source: github

github:
  repo: "OWNER/REPOSITORY"
  branch: "main"
  token_env: "GITHUB_TOKEN"
```

Configura il token in `.env`:

```bash
GITHUB_TOKEN=ghp_inserisci_token_github
```

Se il repository non esiste o non è raggiungibile e non sono disponibili documenti locali completi, il sistema mostra:

```text
Repository GitHub non trovato
```

Se GitHub fallisce ma i quattro documenti esistono in `docs/`, il sistema usa automaticamente il fallback locale e stampa:

```text
[INFO] GitHub non disponibile.
[INFO] Utilizzo documentazione locale.
```

## Ordine operativo documenti

L'ordine di precedenza rimane:

1. `OPERATING_RULES.md`
2. `TPO_SHEETS_SCHEMA.md`
3. `AGENTS.md`
4. `TPO_BOOTSTRAP.md`

## Configurazione Google Sheets API

1. Apri Google Cloud Console.
2. Crea o seleziona un progetto.
3. Abilita `Google Sheets API`.
4. Crea un Service Account.
5. Scarica il file JSON delle credenziali.
6. Salvalo come:

```text
config/google-service-account.json
```

7. Apri il Google Sheet e condividilo con l'email del Service Account, con permesso di sola lettura.
8. Nel file `config/settings.yaml`, imposta:

```yaml
google_sheets:
  spreadsheet_id: "INSERISCI_ID_GOOGLE_SHEET"
  credentials_file: "config/google-service-account.json"
```

Lo `spreadsheet_id` è la parte dell'URL tra `/d/` e `/edit`.

## Esecuzione

```bash
python3 -m src.aggiornami --json
```

La prima versione resta in sola lettura:

```yaml
dry_run: true
```

Non scrive nei fogli e usa lo scope:

```text
https://www.googleapis.com/auth/spreadsheets.readonly
```

## Stock Alarm

Nel foglio `STOCK`, per ogni riga:

```text
DISPONIBILE < PRENOTATO
```

genera:

```text
ALLARME ROSSO
PRIORITÀ ASSOLUTA
```

## Google Sheets Writer

Il Writer applica righe già preparate ai fogli Google Sheets dopo un preflight completo. Non interpreta conversazioni, non inventa dati, non modifica righe esistenti e non cancella righe.

Il service account deve avere permesso Editor sul Google Sheet. Lo scope richiesto per la scrittura è:

```text
https://www.googleapis.com/auth/spreadsheets
```

Formato del piano:

```json
{
  "operations": [
    {
      "sheet_name": "FORNITORI",
      "mode": "append",
      "rows": [
        {
          "ID_FORNITORE": "ESEMPIO-FORNITORE-001",
          "RAGIONE_SOCIALE": "Fornitore Demo Non Reale"
        }
      ]
    }
  ]
}
```

Dry-run:

```bash
python3 -m src.write_sheets --input work/write_plan.example.json --dry-run
```

Apply:

```bash
python3 -m src.write_sheets --input work/write_plan.json --apply
```

Il preflight verifica schema ufficiale, presenza fogli, intestazioni, righe vuote, colonne sconosciute e duplicati. Se una sola operazione non è valida, l'intero piano viene bloccato e non viene scritta nessuna riga. Google Sheets non offre rollback transazionale completo: TowerPower OS riduce il rischio eseguendo tutte le verifiche prima dell'unica richiesta di scrittura.

I duplicati vengono rilevati con chiavi specifiche per foglio. Un duplicato viene segnalato e non scritto.
