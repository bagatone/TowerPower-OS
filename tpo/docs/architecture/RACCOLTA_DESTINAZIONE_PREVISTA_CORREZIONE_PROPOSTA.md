# RACCOLTA — destinazione_prevista via correzione estesa (PROPOSTA)

**Stato:** PROPOSTA — in attesa di approvazione owner. Non introduce alcuna
autorità né autorizza implementazione fino ad approvazione esplicita.
**Ambito:** chiude il gap tra `RACCOLTA_AUTHORITY_FREEZE.md` §10
(`destinazione_prevista` esiste nel modello ma nessun comando la valorizza)
e l'esigenza operativa di segnalare come "prova"/omaggio le RACCOLTE
collegate a ordini generati durante una finestra di sospensione fornitura.
**Origine:** conversazione Owner del 2026-09-10.

## 1. Situazione attuale (verificata sul codice reale)

- `domain/entities/raccolta.py`: `destinazione_prevista` è un campo
  nullable, default `None`.
- `infrastructure/postgresql/raccolta.py`: ENTRAMBI gli INSERT (per
  `raccolta registra` e per `raccolta correggi`) scrivono letteralmente
  `NULL` su questa colonna — nessun comando esistente oggi può valorizzarla.
- `RACCOLTA_AUTHORITY_FREEZE.md` §7 e §15: RACCOLTA è append-only, UPDATE e
  DELETE sono vietati a livello database senza eccezioni. Un comando che
  facesse UPDATE diretto della colonna violerebbe questo Freeze già
  approvato.
- `RACCOLTA_AUTHORITY_FREEZE.md` §10: "`destinazione_prevista` non è
  ASSEGNAZIONE" — resta un campo puramente descrittivo/informativo, mai
  un'autorità di allocazione fisica o cliente.
- `RACCOLTA_CORREZIONE_AUTHORITY_FREEZE.md` (già approvato e implementato,
  comando `raccolta correggi` / `CorreggiRaccolta`): l'unico meccanismo oggi
  autorizzato a "toccare" una RACCOLTA dopo la creazione. Crea una NUOVA
  riga RAC-* di rettifica, collegata all'originale via
  `rettifica_raccolta_id`, con una propria quantità (con segno). Oggi il
  modello di rettifica copre quantità/SEMINA/`effective_at` errati — non
  prevede un caso "quantità invariata, solo annotazione".
- Nessun concetto di "PROVA"/campione/omaggio esiste oggi nel dominio
  (verificato via grep su `src/tpo_core` e `docs/architecture`: nessun hit
  reale).

## 2. Owner Decision (2026-09-10)

- **D2 — Meccanismo: APPROVATA.** Si estende `CorreggiRaccolta` (comando già
  approvato e implementato) per accettare opzionalmente
  `destinazione_prevista` sulla riga di rettifica. Quando la rettifica serve
  solo per annotare (non per correggere una quantità sbagliata), la
  quantità di rettifica è zero — il totale netto dell'evento RACCOLTA non
  cambia, cambia solo l'annotazione visibile sull'ultima rettifica. Nessun
  nuovo meccanismo di scrittura, nessuna riapertura del vincolo append-only
  di `RACCOLTA_AUTHORITY_FREEZE.md`.

## 3. Modello proposto

- `CorreggiRaccolta` (`tpo raccolta correggi`) guadagna un parametro
  opzionale `--destinazione-prevista` (testo libero, es. "PROVA",
  "OMAGGIO").
- Vincolo nuovo, in aggiunta a quelli già in vigore
  (`RACCOLTA_CORREZIONE_AUTHORITY_FREEZE.md` §4): una rettifica con
  quantità zero è ammessa **solo se** accompagnata da un
  `destinazione_prevista` non nullo — altrimenti sarebbe una rettifica
  senza alcun effetto e senza motivo, quindi rifiutata (fallisce chiuso).
- La lettura di RACCOLTA (`semina_raccolta_lettura`) espone
  `destinazione_prevista` come "il valore dell'ultima rettifica che lo
  valorizza, se presente, altrimenti quello dell'evento originario (sempre
  NULL in V1)" — il principio esatto va definito in fase di
  implementazione, ma la regola di fondo è: l'informazione più recente
  vince, senza mai riscrivere la storia (coerente con PRINCIPIO 4).
- Resta vietato usare `destinazione_prevista` come ASSEGNAZIONE (§10,
  invariato): è un'etichetta descrittiva, non un'autorità di allocazione
  fisica o cliente. Segnare una RACCOLTA come "PROVA" non sposta né libera
  alcuna ASSEGNAZIONE_FISICA esistente — quello resta un dominio distinto,
  fuori scope.

## 4. Effetto pratico per il caso concreto

Per gli ordini già generati in una finestra di sospensione che si vogliono
trattare come regalie: si esegue `raccolta correggi` sulla/e RACCOLTA
collegata/e, quantità di rettifica 0, `--destinazione-prevista PROVA`. La
RACCOLTA originale resta intatta e leggibile (nessuna riscrittura), la
nuova rettifica RAC-* zero-quantità porta l'annotazione, e l'ORDINE/CONSEGNA
a monte restano quello che sono (Owner Decision D2 di
`PROGRAMMA_FORNITURA_SOSPENSIONE_RIATTIVAZIONE_PROPOSTA.md`: gli ordini già
generati non vengono toccati direttamente).

## 5. Guardie proposte

- Vietato UPDATE/DELETE diretto su RACCOLTA per qualunque motivo, invariato.
- Vietata una rettifica quantità-zero senza `destinazione_prevista`
  valorizzato (altrimenti sarebbe un no-op senza causale).
- Vietato usare `destinazione_prevista` per esprimere ASSEGNAZIONE,
  proprietà cliente o allocazione fisica (§10, invariato).
- Nessun vocabolario controllato per `destinazione_prevista` in questa
  proposta: resta testo libero, come già previsto dal campo esistente
  (nessuna "QUALITY AUTHORITY", §10, resta DEFERRED).

## 6. Fuori scope

- Un concetto formale di "PROVA" come stato/dominio proprio (scartato in
  favore dell'annotazione libera su un campo già esistente).
- Propagazione dell'annotazione a STOCK, MOVIMENTO_MAGAZZINO, FATTURA
  (`RACCOLTA_AUTHORITY_FREEZE.md` §11, invariato).
- Reportistica/filtri dedicati sulle RACCOLTE annotate come "PROVA" (si può
  aggiungere in futuro leggendo il campo, non serve autorizzazione
  aggiuntiva).

## 7. Prossimo passo

In attesa di approvazione owner. Se approvata: estensione del comando
esistente (domain, application, writer, CLI, test), aggiornamento di
`RACCOLTA_CORREZIONE_AUTHORITY_FREEZE.md` per registrare l'estensione (non
la contraddice: aggiunge un caso ammesso in più), stesso standard di
copertura già raggiunto.
