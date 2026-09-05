# MOVIMENTI_MAGAZZINO

**Stato:** ARCHITECTURE FREEZE v1.0

## Scopo

Il Register MOVIMENTI_MAGAZZINO definisce gli eventi autorizzati che modificano lo STOCK nel Tower Power Operations e ne preserva la tracciabilità storica.

Il Register mantiene separati gli eventi che determinano le variazioni dalla rappresentazione dello stato corrente conservata nel Register STOCK.

## Definizione

Un MOVIMENTO rappresenta esclusivamente un evento che modifica lo STOCK.

Ogni MOVIMENTO possiede un identificativo univoco, permanente e semanticamente neutro e modifica esclusivamente lo STOCK di una sola VARIETÀ, registrando la variazione di quantità determinata dall'evento autorizzato.

MOVIMENTI_MAGAZZINO è l'unico Register autorizzato a modificare lo STOCK. Lo STOCK non può essere modificato direttamente e ogni sua variazione deve derivare esclusivamente da un MOVIMENTO autorizzato.

## Principi Architetturali

- MOVIMENTI_MAGAZZINO rappresenta esclusivamente gli eventi che modificano lo STOCK.
- Ogni MOVIMENTO possiede un identificativo univoco, permanente e semanticamente neutro.
- Ogni MOVIMENTO è immutabile dopo la registrazione.
- Gli errori vengono corretti mediante un nuovo MOVIMENTO e mai modificando quello esistente.
- Lo STOCK non può essere modificato direttamente.
- Ogni variazione dello STOCK deriva esclusivamente da un MOVIMENTO autorizzato.
- MOVIMENTI_MAGAZZINO è l'unico Register autorizzato a modificare lo STOCK.
- Ogni MOVIMENTO modifica esclusivamente lo STOCK di una sola VARIETÀ.
- L'origine costituisce il contesto del MOVIMENTO e non ne modifica l'identità.
- MOVIMENTI_MAGAZZINO non mantiene una relazione diretta con SEMINE.
- Lo STOCK rappresenta esclusivamente lo stato corrente; MOVIMENTI_MAGAZZINO rappresenta esclusivamente gli eventi che determinano tale stato.

## Natura dell'evento

Il MOVIMENTO è un evento che produce una variazione dello STOCK.

I tipi iniziali di MOVIMENTO sono:

- CARICO;
- SCARICO;
- RETTIFICA.

Il tipo identifica esclusivamente la natura della variazione dello STOCK e non l'evento che l'ha originata.

Il modello consente l'introduzione futura di ulteriori tipi di MOVIMENTO senza modificare l'architettura del Register.

Il MOVIMENTO può derivare da:

- RACCOLTA;
- CONSEGNA;
- SCARTO;
- RETTIFICA;
- altro evento autorizzato.

L'origine documenta il contesto nel quale si determina la variazione dello STOCK e non modifica l'identità del MOVIMENTO.

## Relazioni Architetturali

### STOCK

```text
MOVIMENTO autorizzato
↓
variazione dello STOCK
```

MOVIMENTI_MAGAZZINO è l'unico Register autorizzato a modificare lo STOCK.

Lo STOCK rappresenta esclusivamente lo stato corrente e non registra gli eventi che lo modificano. MOVIMENTI_MAGAZZINO conserva gli eventi che determinano tale stato.

### VARIETÀ

Ogni MOVIMENTO modifica esclusivamente lo STOCK di una sola VARIETÀ.

Il riferimento alla VARIETÀ identifica il prodotto il cui STOCK viene modificato e non altera l'identità del MOVIMENTO.

### RACCOLTE

Una RACCOLTA può costituire l'origine di un MOVIMENTO autorizzato.

La RACCOLTA non modifica automaticamente lo STOCK. La variazione dello STOCK avviene esclusivamente attraverso il MOVIMENTO che ne deriva.

### CONSEGNE

Una CONSEGNA può costituire l'origine di un MOVIMENTO autorizzato.

La variazione dello STOCK appartiene a MOVIMENTI_MAGAZZINO e non al Register CONSEGNE.

### SCARTI

Uno SCARTO può costituire l'origine di un MOVIMENTO autorizzato.

La variazione dello STOCK appartiene a MOVIMENTI_MAGAZZINO e non al Register specialistico che registra lo SCARTO.

### RETTIFICHE

Una RETTIFICA può costituire l'origine di un MOVIMENTO autorizzato.

La RETTIFICA dello STOCK viene rappresentata da un nuovo MOVIMENTO e non dalla modifica di un MOVIMENTO esistente o dello STOCK.

### SEMINE

MOVIMENTI_MAGAZZINO non mantiene una relazione diretta con SEMINE.

La relazione con la SEMINA, quando necessaria, è ricostruibile attraverso gli altri Register.

## Dati Minimi Obbligatori

Ogni MOVIMENTO deve registrare almeno i seguenti dati:

- identificativo permanente;
- VARIETÀ;
- tipo di movimento;
- quantità;
- unità di misura;
- verso della variazione (+ / −);

  Il verso della variazione rappresenta esclusivamente l'effetto quantitativo del MOVIMENTO sullo STOCK ed è distinto dal tipo di MOVIMENTO.
- data;
- motivo.

Possono essere presenti informazioni aggiuntive purché non alterino il significato architetturale del Register.

## Integrità Storica

Ogni MOVIMENTO rappresenta un evento registrato in modo permanente.

L'identità del MOVIMENTO non cambia nel tempo.

Il MOVIMENTO è immutabile dopo la registrazione e non viene modificato per correggere un errore.

Ogni correzione viene registrata mediante un nuovo MOVIMENTO, preservando il MOVIMENTO esistente e la tracciabilità della variazione dello STOCK.

La sequenza cronologica dei MOVIMENTI costituisce lo storico ufficiale delle variazioni dello STOCK.

Lo STOCK non conserva lo storico delle proprie variazioni. Tale storico appartiene esclusivamente a MOVIMENTI_MAGAZZINO.

## Principi di Evoluzione

Nuovi tipi di MOVIMENTO e informazioni aggiuntive potranno essere introdotti esclusivamente se:

- non modificano il significato architetturale del MOVIMENTO;
- non trasformano MOVIMENTI_MAGAZZINO in una rappresentazione dello stato corrente;
- non consentono modifiche dirette dello STOCK;
- non alterano l'immutabilità dei MOVIMENTI già registrati;
- non introducono una relazione diretta con SEMINE;
- mantengono la compatibilità con le versioni precedenti;
- rispettano integralmente REGISTER_GOVERNANCE.

MOVIMENTI_MAGAZZINO deve continuare a rappresentare esclusivamente gli eventi autorizzati che determinano lo stato corrente dello STOCK.

## Appendice: Estensione ad ARTICOLO (ARTICOLO_AUTHORITY_FREEZE.md)

Il principio "Ogni MOVIMENTO modifica esclusivamente lo STOCK di una sola VARIETÀ" (sopra) viene esteso, non sostituito: ogni MOVIMENTO modifica esclusivamente lo STOCK di una sola VARIETÀ oppure lo STOCK_ARTICOLI di un solo ARTICOLO, mai entrambi e mai nessuno dei due.

ARTICOLO identifica i materiali che servono alla catena produttiva perché funzioni (substrati, fertilizzante, packaging, e simili) — una Configuration distinta da VARIETA (i semi), congelata da ARTICOLO_AUTHORITY_FREEZE.md.

STOCK_ARTICOLI è una tabella parallela a STOCK, con la stessa forma e gli stessi principi di integrità di STOCK.md applicati ad ARTICOLO anziché a VARIETA: disponibilità puramente fisica, nessuna quantità negativa, incremento/decremento esclusivamente tramite MOVIMENTO_MAGAZZINO autorizzato. STOCK.md non viene modificato: continua a governare esclusivamente STOCK/VARIETA.

Un MOVIMENTO su ARTICOLO non deriva mai da RACCOLTA o CONSEGNA (origini fisicamente specifiche di VARIETA): la sua origine è sempre esterna a quell'insieme. Questa estensione non introduce alcuna relazione diretta tra MOVIMENTI_MAGAZZINO e SEMINE, non trasforma MOVIMENTI_MAGAZZINO in una rappresentazione dello stato corrente, non consente modifiche dirette allo STOCK/STOCK_ARTICOLI, e non altera l'immutabilità dei MOVIMENTI già registrati.
