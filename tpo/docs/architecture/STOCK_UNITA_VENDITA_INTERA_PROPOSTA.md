# STOCK a unità intera (SET) per prodotto mai tagliato — PROPOSTA

Stato: SUPERATA da `docs/architecture/MOVIMENTO_CARICO_AUTHORITY_FREEZE.md`
§11 (19/9/2026) — vedi "Esito reale (19/9/2026)" in fondo a questo
documento. Owner Decision 1 sotto resta valida e implementata; Owner
Decision 2 e l'"Alternativa scartata" sono state superate dai fatti
(l'Owner Decision 2 qui sotto si è rivelata non eseguibile). Documento
mantenuto per la cronologia del ragionamento, non più la fonte di verità
sullo schema STOCK.

Segue lo stile delle Freeze/proposte esistenti del repo (situazione reale
verificata sul codice → Owner Decision → modello proposto → guardie →
fuori scope → prossimo passo).

## Situazione reale verificata (19/9/2026)

- I microgreens di Tower Power non vengono mai tagliati: si vendono il
  SET intero (substrato incluso) così com'è. La futura produzione di
  verdura in torre verticale sarà invece tagliata e pesata.
- `tpo.righe_ordine.unita_misura` è sempre `SET` per gli ordini reali
  oggi esistenti.
- `tpo.stock` ha `varieta_id` come **chiave primaria** (non solo
  vincolo unique) — confermato in `migrations/versions/
  20260810_0004_production_execution_prerequisites.py`. Significa che
  ogni VARIETA può avere **una sola unità di misura di stock per
  sempre**, non due contemporaneamente.
- `tpo movimento carica-raccolta` (`infrastructure/postgresql/
  movimento_carico.py`, `_lock_or_create_stock`) crea sempre lo stock in
  `GRAM`, hardcoded, nessuna eccezione. È l'unico percorso governato
  oggi esistente per far nascere STOCK di una VARIETA.
- `delivery_fulfilment_writer.py` è già agnostico rispetto all'unità:
  richiede solo che riga ordine, riga consegna e stock coincidano tutti
  sulla stessa unità — non è lui il problema, è che oggi non esiste
  alcun modo di popolare stock in SET.
- Conseguenza pratica: **nessuna consegna di microgreens è oggi
  registrabile**, perché lo stock nasce sempre in GRAM ma gli ordini
  sono sempre in SET.
- Oggi stesso (19/9), come soluzione temporanea per tracciare raccolti
  reali già avvenuti, sono stati creati via `carica-raccolta` due righe
  STOCK in GRAM: Afila (VAR-000001) 933g, Cilantro (VAR-000003) 408g.
  Queste righe **andranno ritirate** per liberare la chiave primaria
  prima di poter creare lo stock in SET per le stesse varietà (vedi
  Owner Decision 2).

## Owner Decision 1 — come nasce lo STOCK in SET

Proposta: estendere `tpo movimento carica-raccolta` con un nuovo
argomento `--unita-misura {GRAM,SET}` (default `GRAM`, comportamento
attuale invariato per compatibilità):

- `GRAM` (percorso attuale, invariato): richiede `--quantita-pesata`,
  peso dichiarato dall'operatore, mai calcolato — resta valido per la
  futura verdura in torre verticale tagliata/pesata.
- `SET` (nuovo): **nessun peso da dichiarare**. La quantità caricata a
  stock è esattamente la quantità SET già dichiarata sulla RACCOLTA
  collegata (`raccolta record --quantity --uom SET`) — non è un numero
  nuovo da inventare o calcolare da un fattore di resa, è lo stesso
  numero già reale, perché per un prodotto mai tagliato "N SET
  raccolti" e "N SET a magazzino" sono la stessa unità fisica, senza
  passaggi intermedi che introducano incertezza.

`_lock_or_create_stock` guadagna un parametro per l'unità target; se
esiste già una riga STOCK per quella VARIETA in un'unità diversa, il
comando fallisce chiuso con lo stesso errore già esistente
(`STOCK_UNIT_MISMATCH`), mai una scrittura silenziosa incoerente.

## Owner Decision 2 — cosa fare dello STOCK in GRAM già creato oggi per Afila/Cilantro

Non esiste (verificato: nessun `rettifica` per STOCK di VARIETA, solo
per ARTICOLO e FATTURA) un comando governato per ritirare/convertire una
riga STOCK esistente. Poiché `varieta_id` è chiave primaria, non si può
avere contemporaneamente una riga GRAM e una riga SET per la stessa
VARIETA.

Proposta (unica strada pulita senza un nuovo comando dedicato, dato che
i dati di oggi sono un caso isolato, non uno storico da preservare
esattamente in quella forma): una migrazione dati **una tantum**,
eseguita da Matteo con lo stesso schema già usato per
`migrate_to_head.sh` (Secret Boundary, mai stampa credenziali), che:
1. Converte la riga STOCK esistente di Afila da `933 GRAM` a `3 SET`
   (933g / oggi rappresentati come 3 SET: 1 Callao + 2 Selvaje, la
   quantità SET è già nota con certezza dalle RACCOLTE di oggi, non va
   ricalcolata da un peso).
2. Stessa cosa per Cilantro: da `408 GRAM` a `2 SET` (1 Azul y Sal + 1
   Selvaje).
3. Le RACCOLTE e i MOVIMENTI_MAGAZZINO di oggi (RAC-000001..4,
   MOV-000001..4) **restano invariati** — sono eventi storici reali
   (quanto pesava quel giorno), non vanno riscritti; cambia solo la
   riga STOCK corrente, che è un aggregato di oggi, non un evento
   storico.
4. Aggiunge una riga `audit_eventi` che documenta la conversione
   (before/after, motivo: "conversione una tantum GRAM->SET, primo
   utilizzo del percorso SET, nessuna consegna ancora effettuata contro
   questo stock").

Alternativa scartata: cambiare la chiave primaria di `tpo.stock` in
`(varieta_id, unita_misura)` per permettere entrambe le unità
contemporaneamente per la stessa VARIETA. Scartata perché: (a) tocca una
foreign key già esistente da `movimenti_magazzino`, migrazione più
invasiva; (b) nella realtà del business di oggi nessuna varietà viene
mai venduta sia a unità intera sia a peso contemporaneamente — un solo
percorso per varietà riflette la realtà, non la limita.

## Guardie (invariate dal disegno esistente)

- `GRAM` resta l'unico percorso con peso dichiarato dall'operatore — mai
  toccato, resta per la futura verdura in torre verticale.
- `SET` non introduce alcun fattore di resa/calcolo: il numero che va a
  stock è sempre lo stesso numero già dichiarato sulla RACCOLTA, mai
  derivato.
- Nessuna VARIETA può avere stock in due unità contemporaneamente
  (`STOCK_UNIT_MISMATCH` fallisce chiuso).
- `delivery_fulfilment_writer.py` non viene toccato: è già corretto e
  agnostico rispetto all'unità.

## Fuori scope

- Non tocca in alcun modo `raccolta record` (resta identico).
- Non introduce un comando di correzione/rettifica STOCK generico per
  VARIETA — resta un gap noto se servirà in futuro per altri casi (non
  necessario per questo mini-progetto, la conversione di oggi è una
  migrazione dati una tantum, non un comando ripetibile).
- Non tocca `resa_unita_misura` su `protocollo_versioni` (oggi sempre
  `SET` hardcoded in `agronomic_commissioning.py`) né introduce una
  regola automatica che deduce l'unità di CARICO dal protocollo — resta
  una scelta esplicita dell'operatore ad ogni comando (`--unita-misura`),
  più semplice e più in linea con "mai invenzione silenziosa".

## Prossimo passo

In attesa di conferma di Matteo/Giulia su Owner Decision 1 e 2 prima di
scrivere codice applicativo/infrastrutturale e la migrazione dati.


## Esito reale (19/9/2026)

L'Owner Decision 2 qui sopra (semplice `UPDATE tpo.stock SET
unita_misura='SET' ...`) si è rivelata **non eseguibile**: tentata in
pratica, è fallita con `psycopg.errors.ForeignKeyViolation` — i 4
MOVIMENTI_MAGAZZINO storici in GRAM (MOV-000001..4) referenziano quella
riga STOCK con una foreign key `ON UPDATE RESTRICT` e sono immutabili per
definizione, quindi l'unità di misura di quella riga non può mai cambiare
in place.

L'"Alternativa scartata" (chiave composita `(varieta_id,unita_misura)`) è
diventata la scelta finale, per Owner Decision esplicita di Matteo ("o
facciamo tutto in grammi o tutto in set, non me la sento di lasciare due
varieta in grammi e il resto in set") che ha esteso la scelta oltre
Afila/Cilantro a un principio generale: mai una VARIETA permanentemente
mista, da applicare uniformemente. Dettagli completi, motivazione e design
finale in `docs/architecture/MOVIMENTO_CARICO_AUTHORITY_FREEZE.md` §11 e
nella migrazione `migrations/versions/20260919_0035_stock_unita_composita.py`.
La migrazione dati una tantum (Owner Decision 2 qui sopra) è stata
riscritta di conseguenza: azzera la riga GRAM in place (nessun cambio di
unità, nessun conflitto di foreign key) e inserisce una nuova riga SET,
invece di aggiornare la riga esistente.
