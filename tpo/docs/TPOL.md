# TPOL.md

## TowerPower Operational Language v1

TPOL è il linguaggio operativo di TowerPower OS.

TPOL non è un linguaggio di programmazione. TPOL è il linguaggio con cui operatori, ChatGPT, dashboard, API e futuri agenti comunicano con TowerPower OS.

Il suo scopo è trasformare frasi naturali in eventi operativi coerenti, verificabili e compatibili con le regole ufficiali del sistema.

## 1. Principio

Ogni informazione fornita dall'operatore rappresenta un evento operativo.

L'operatore descrive ciò che è successo.

TowerPower OS interpreta il significato operativo.

TPOL non autorizza scritture dirette sui fogli. Ogni frase deve essere interpretata, validata e trasformata in un evento logico prima di qualunque aggiornamento.

## 2. Sorgenti

TPOL è indipendente dalla sorgente.

Le sorgenti possono essere:

- Chat
- CLI
- Dashboard
- API
- Mobile
- Voce

La stessa informazione deve produrre lo stesso evento logico, indipendentemente dal canale usato.

## 3. Verbi operativi

I verbi operativi indicano l'azione principale descritta dall'operatore.

### Produzione

- seminare
- idratare
- passare a luce
- raccogliere
- scartare

### Commerciale

- aggiungere cliente
- modificare ordine
- sospendere cliente
- riattivare cliente
- consegnare
- ricevere pagamento

### Magazzino

- acquistare
- ricevere
- consumare
- correggere inventario

### Impianto

- cambiare soluzione
- manutenzione
- pulizia

### Photo Bank

- fotografare
- associare foto
- validare foto

## 4. Oggetti

Gli oggetti ufficiali indicano le entità operative coinvolte in un evento.

- cliente
- ordine
- lotto
- varietà
- set
- vaschetta
- torre
- substrato
- semi
- fertilizzante
- foto
- fornitore

## 5. Tempo

Le espressioni temporali in TPOL devono essere interpretate dal Calendar Engine.

Esempi:

- oggi
- domani
- tra due giorni
- ogni martedì
- ogni due settimane

Il Calendar Engine deve convertire queste espressioni in date assolute prima che l'evento possa diventare pronto per un WritePlan.

In caso di ambiguità, TowerPower OS deve chiedere conferma all'operatore.

## 6. Quantità

TPOL riconosce unità operative e quantità espresse in modo naturale.

Unità riconosciute:

- set
- vaschette
- grammi
- kg
- litri
- pezzi
- torri

Le quantità devono essere mantenute come dati dichiarati dall'operatore. TowerPower OS non deve inventare quantità mancanti.

## 7. Risultato

Ogni frase TPOL deve produrre:

- un solo evento principale;
- eventuali eventi secondari;
- mai scritture dirette.

Gli eventi secondari sono ammessi quando derivano chiaramente dall'evento principale, ma devono essere validati prima di qualunque aggiornamento.

## 8. Esempi

### Esempio 1

Frase:

> Ho seminato 6 set di cilantro.

Risultato:

```text
EVENTO
SEMINA
```

### Esempio 2

Frase:

> Buenaonda vuole una cassa ogni due venerdì.

Risultato:

```text
NUOVO_ORDINE_RICORRENTE
```

### Esempio 3

Frase:

> Ho raccolto 2 set di mizuna.

Risultato:

```text
RACCOLTA
```

### Esempio 4

Frase:

> Ho cambiato la soluzione.

Risultato:

```text
CAMBIO_SOLUZIONE
```

## 9. Principi

TPOL deve essere:

- semplice
- naturale
- leggibile
- indipendente dalla tecnologia
- estendibile
- compatibile con tutti gli agenti

TPOL deve aiutare TowerPower OS a capire eventi reali senza dedurre o inventare dati operativi.
