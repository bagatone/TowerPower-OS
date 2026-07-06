# TPO_BOOTSTRAP.md

TPO deve usare `OPERATING_RULES.md` come fonte ufficiale delle regole operative.

TPO deve usare `AGENTS.md` come riferimento per il comportamento degli agenti.

Se TPO non può leggere direttamente questi file, l'utente deve incollare le regole rilevanti nella chat.

In caso di conflitto tra memoria della chat, output precedente o supposizioni, prevale `OPERATING_RULES.md`.

## Regole Critiche Da Ricordare

- El Pellizco è sospeso e non è cliente ricorrente attivo.
- Salvaje è cliente attivo prioritario.
- PREDB è solo per lotti/raccolti storici precedenti alla codifica ufficiale.
- STOCK: DISPONIBILE = pronto oggi; PRENOTATO = consegne future attive; VENDIBILE = DISPONIBILE - PRENOTATO.
- CONSEGNE deve essere ordinato per PROSSIMA_CONSEGNA.
- Lo Nuestro = 8 varietà x 0.5 set, esclusa Mostaza.
- Cilantro Margot 17/07 = lotto in germinazione ex Pellizco, non cilantro già pronto.
- Mizuna confermata: MIZ-2306-A e MIZ-2806-A.
- PROBLEMI deve leggere i problemi aperti reali: Mostaza, Hinojo, Rábano in osservazione.

## Comando da incollare in TPO

```text
Da ora in avanti usa OPERATING_RULES.md come fonte ufficiale delle regole operative Tower Power e AGENTS.md come riferimento per il comportamento degli agenti.

Se non puoi leggere direttamente questi file, chiedimi di incollare le sezioni rilevanti prima di prendere decisioni operative.

In caso di conflitto tra memoria della chat, output precedente, supposizioni, fogli o agenti, prevale OPERATING_RULES.md.

Regole critiche:
- El Pellizco è sospeso e non è cliente ricorrente attivo.
- Salvaje è cliente attivo prioritario.
- PREDB è solo per lotti/raccolti storici precedenti alla codifica ufficiale.
- STOCK: DISPONIBILE = pronto oggi; PRENOTATO = consegne future attive; VENDIBILE = DISPONIBILE - PRENOTATO.
- CONSEGNE deve essere ordinato per PROSSIMA_CONSEGNA.
- Lo Nuestro = 8 varietà x 0.5 set, esclusa Mostaza.
- Cilantro Margot 17/07 = lotto in germinazione ex Pellizco, non cilantro già pronto.
- Mizuna confermata: MIZ-2306-A e MIZ-2806-A.
- PROBLEMI deve leggere i problemi aperti reali: Mostaza, Hinojo, Rábano in osservazione.
```

# TPO QUICK BOOTSTRAP

## Fonti ufficiali

1. OPERATING_RULES.md
   - regole operative ufficiali

2. TPO_SHEETS_SCHEMA.md
   - schema ufficiale dei Google Sheets

3. AGENTS.md
   - comportamento degli agenti

## Regole

- Non inventare dati.
- Se un dato manca usare DA CONFERMARE.
- Per le regole operative prevale OPERATING_RULES.md.
- Per la struttura dei fogli prevale TPO_SHEETS_SCHEMA.md.
- Tutti gli output destinati ai fogli devono essere compatibili con Google Sheets.
- Pubblicare intestazioni sempre in una sola riga separata da "|".
- Generare quando possibile righe pronte da copiare nei fogli.

## Schemi ufficiali

CLIENTI:
CLIENTE | FREQUENZA | GIORNO | STATO | NOTE

CONSEGNE:
CLIENTE | PRODOTTO | QUANTITA | UNITA | ID_LOTTO | STATO | GIORNO_CONSEGNA | FREQUENZA | PROSSIMA_CONSEGNA | NOTE

LOTTI:
CALENDARIO_PROD | SET | VARIETA | DATA_SEMINA | DATA_PASSAGGIO | FASE | STATO | DATA_RACCOLTA | NOTE

SEMINE:
DATA | ID_LOTTO | VARIETA | SET | GRAMMI_SEME | INIZIO_IDRATAZIONE | DATA_SEMINA | OPERATORE | NOTE

RACCOLTI:
DATA_RACCOLTA | ID_LOTTO | VARIETA | SET_RACCOLTI | DESTINAZIONE | OPERATORE | QUALITA | NOTE

STOCK:
VARIETA | DISPONIBILE | PRENOTATO | VENDIBILE | NOTE | ULTIMO_AGGIORNAMENTO

MASTER_VARIETA:
VARIETA | CODICE | GRAMMI_SET | IDRATAZIONE_ORE | GERMINAZIONE_GG | LUCE_GG | TOTALE_GG | STATO | NOTE

PROBLEMI:
DATA | AREA | GRAVITA | PROBLEMA | AZIONE_RICHIESTA | STATO | DATA_CHIUSURA | NOTE

PIANO_SEMINE:
DATA_IDRATAZIONE | DATA_SEMINA | VARIETA | SET | CLIENTE_DESTINAZIONE | DATA_CONSEGNA_PREVISTA | PRIORITA | STATO | NOTE

CALENDARIO_PRODUZIONE:
DATA | EVENTO | VARIETA | SET | ID_LOTTO | CLIENTE_COLLEGATO | FASE | STATO | PRIORITA | NOTE

PIANO_EXTRA:
DATA_CICLO | VARIETA | SET_EXTRA | MOTIVO | CONFERMATO | NOTE

BRIEFING_GIORNALIERO:
DATA | COSA_FARE_OGGI | SEMINE | LOTTI_IN_GERMINAZIONE | LOTTI_SOTTO_LUCE | RACCOLTI_PREVISTI | CONSEGNE_PREVISTE | PROBLEMI_APERTI | NOTE
