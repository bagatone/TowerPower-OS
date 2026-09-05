# Walkthrough CLI end-to-end

Dimostra che l'intera catena TPO funziona insieme, chiamando il vero
binario CLI di produzione (`python -m src.tpo_core.cli.main`) passo per
passo, su un cluster PostgreSQL locale, isolato e usa-e-getta — **mai** il
database reale (Supabase/`.env.local`).

Catena coperta: onboarding cliente/varietà → listino prezzi →
configurazione fatturazione → SEMENTE → SEMENTE_IMPIEGO → LOTTO_SEME →
SEMINA (commissioning + transizioni di stato fino a
`PRONTA_ALLA_RACCOLTA`) → RACCOLTA → MOVIMENTO_MAGAZZINO (carico) →
CONSEGNA (delivery fulfil) → ASSEGNAZIONE_FISICA → FATTURA → INCASSO,
chiusa da una query di traccia end-to-end e da una verifica del servizio
di sola lettura DISPONIBILITA_COMMERCIALE (PRENOTATO/VENDIBILE).

Non copre (deliberatamente, per restare un primo giro leggibile):
ARTICOLO/MOVIMENTO_MAGAZZINO-ARTICOLO, USCITA, correzioni/rettifiche
(RACCOLTA_CORREZIONE, RECTIFY_FATTURA, correzione INCASSO/USCITA),
production planning/scheduling. Ognuno di questi ha già copertura pytest
dedicata; possono diventare un secondo giro di walkthrough se utile.

## Requisiti

- Virtualenv di progetto già creato: `./bootstrap.sh`.
- `initdb` e `pg_ctl` sul PATH (li usa già la tua suite pytest per i test
  di integrazione PostgreSQL reali — se `pytest` ti gira con solo "8
  skipped" li hai già).
- `openssl` sul PATH (di serie su macOS) — serve per un certificato TLS
  self-signed usa-e-getta: le impostazioni di produzione richiedono
  `sslmode` in `require`/`verify-ca`/`verify-full`, coerente con Supabase.

## Uso

```
.venv/bin/python scripts/walkthrough/e2e_walkthrough.py
```

Il cluster disponibile viene avviato in una directory temporanea, il
database viene creato e migrato a head, l'intera catena viene eseguita
stampando ogni comando reale e il suo output, poi il cluster viene
fermato e la directory temporanea rimossa: nessuna traccia sul disco a
fine esecuzione.

Per lasciare il cluster attivo a fine esecuzione (o dopo un errore) e
ispezionarlo manualmente con `psql`:

```
.venv/bin/python scripts/walkthrough/e2e_walkthrough.py --keep
```

Lo script stampa la stringa di connessione e il comando per fermarlo
quando non serve più.

## Se qualcosa fallisce

Lo script si ferma al primo comando che restituisce un exit code
inatteso, stampa l'errore e (a meno che il cluster non sia già stato
fermato) lascia il database attivo per ispezione. Incolla l'output
completo per la diagnosi — stessa logica già seguita per i round di
`pytest` reali di questa sessione.
