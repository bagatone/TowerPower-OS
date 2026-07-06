# OPERATING_RULES.md

## 1. Scopo

Questo documento contiene le regole operative ufficiali di Tower Power.

In caso di conflitto tra chat, agenti, fogli o interpretazioni, OPERATING_RULES.md prevale.

Ogni nuova regola operativa permanente decisa dall'utente deve essere registrata qui.

Se una regola non è presente in OPERATING_RULES.md, non può essere considerata ufficiale.

## 2. Clienti

### Clienti attivi principali

- Salvaje
- Sal y Mar / Vaca Azul
- Jaira
- El Callao
- Lo Nuestro
- Margot

### Clienti variabili

- Alquimia

### Clienti sospesi

- El Pellizco

Regola cliente sospeso:
un cliente sospeso non riceve allocazioni produttive, non genera nuove semine, non genera prenotazioni stock e non compare tra i clienti ricorrenti attivi finché non viene riattivato esplicitamente dall'utente.

El Pellizco:
STATO = SOSPESO.
Non allocare produzione.
Non generare nuove semine.
Non considerarlo cliente ricorrente attivo.

Salvaje:
cliente strategico prioritario.
Deve sempre essere incluso in briefing, pianificazione e controlli commerciali quando ha fabbisogni aperti.

## 3. Lotti

Regola base:
1 lotto = stessa varietà + stessa semina + stesso momento operativo.

Formato ID lotto:
AAA-GGMM-L

Esempi:
AFI-2806-A
CIL-0107-A
RAB-3006-B
MIZ-2806-A

Codici varietà ufficiali:
AFI = Guisante Afila
CIL = Cilantro
RAB = Rábano Morado
MIZ = Mizuna Roja
COL = Col Roja
MOS = Mostaza
GIR = Girasole
HIN = Hinojo
LEN = Lenticchie

Regola lotti storici:
i lotti esistenti prima dell'introduzione del sistema di codifica possono ricevere codifica retroattiva eccezionale.

Questa regola vale solo per storico pre-database.
Non usarla per lotti nuovi.

Codici PREDB:
PREDB = codici retroattivi eccezionali per raccolti/consegne storiche precedenti alla tracciabilità ufficiale.
Non sostituire i codici PREDB già approvati.

## 4. Stock

Definizioni ufficiali:

DISPONIBILE = prodotto pronto oggi.

PRENOTATO = somma delle consegne future attive presenti nel foglio CONSEGNE.

VENDIBILE = DISPONIBILE - PRENOTATO.

Regole:

- STOCK è la fonte ufficiale della disponibilità commerciale.
- CONSEGNE è la fonte ufficiale dei prodotti prenotati.
- LOTTI è la fonte ufficiale delle colture in crescita.
- Se VENDIBILE < 0, indicare deficit.
- Se VENDIBILE = 0, non proporre vendite extra.
- Se VENDIBILE > 0, il prodotto può essere proposto a nuovi clienti.

## 5. Consegne

CONSEGNE è la fonte ufficiale degli impegni commerciali futuri.

Le consegne devono essere ordinate cronologicamente usando PROSSIMA_CONSEGNA.

Non mostrare una singola consegna futura se esistono consegne precedenti o contemporanee già pianificate.

Ordine corretto noto al 05/07/2026:

- 09/07/2026 Lo Nuestro
- 09/07/2026 Salvaje
- 10/07/2026 El Callao
- 10/07/2026 Sal y Mar / Vaca Azul
- 17/07/2026 Margot
- 18/07/2026 Jaira

Lo Nuestro:
ordine totale = 4 set.
Composizione = 8 varietà x 0.5 set.
Esclude Mostaza.

## 6. Pianificazione

PIANO_SEMINE è un foglio operativo leggero.
Contiene solo attività future o in corso.

Non deve diventare storico.

Il Planning Agent deve usare VENDIBILE, non DISPONIBILE, per decidere se generare nuove semine.

MASTER_VARIETA è la fonte ufficiale di grammature e cicli produttivi.

## 7. Cilantro / Margot

Il cilantro pronto il 05/07 non può essere assegnato a Margot 17/07.

Il cilantro destinato a Margot 17/07 è il lotto in germinazione ex Pellizco, non il cilantro già pronto.

Dato confermato:
Cilantro = 8.5 set in luce nella finestra utile di consegna + 1 set in germinazione.

## 8. Mizuna

Lotti Mizuna confermati:

- MIZ-2306-A
- MIZ-2806-A

MIZ-2806-A:

- 1 set
- semina/germinazione: 28/06/2026
- passaggio luce: 04/07/2026

## 9. Problemi

PROBLEMI contiene solo problemi operativi della farm.

Non inserire problemi amministrativi o commerciali in PROBLEMI.

Problemi aperti noti al 05/07/2026:

- Mostaza con collasso degli steli e marciume radicale.
- Hinojo con germinazione scarsa.
- Stress fisiologico rábano giorno 1 luce.

La sezione Problemi Aperti del briefing deve essere generata dal foglio PROBLEMI.

Non usare "Problemi agronomici aperti: DA CONFERMARE" se esistono problemi aperti registrati.

## 10. Briefing

AGGIORNAMI deve rispettare OPERATING_RULES.md.

Prima di generare un briefing deve considerare:

- CLIENTI
- CONSEGNE
- STOCK
- LOTTI
- PROBLEMI

Le priorità del giorno devono privilegiare attività operative della farm rispetto a verifiche amministrative quando sono presenti colture da monitorare o problemi aperti.
