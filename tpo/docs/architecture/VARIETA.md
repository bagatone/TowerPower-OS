# Register VARIETÀ

**Stato del documento:** ARCHITECTURE FROZEN v1.0  
**Natura:** documento architetturale ufficiale del Tower Power Operations (TPO)

## 1. Scopo

Il Register VARIETÀ rappresenta l’identità produttiva generale delle colture che Tower Power può produrre e organizza la conoscenza tecnica stabile sviluppata nel tempo.

VARIETÀ non è un’enciclopedia botanica né un catalogo commerciale. Non rappresenta una singola referenza sementiera, un lotto fisico di seme o le osservazioni operative relative a singole SEMINE o RACCOLTE.

Questo documento definisce responsabilità, livelli concettuali, relazioni, ciclo di vita, gestione della conoscenza, protocolli, sementi, lotti di seme, tracciabilità, versionamento e confini del Register. Non definisce lo schema tecnico definitivo dei campi né una sua implementazione.

## 2. Principio fondativo

> **Ogni stagione deve lasciare Tower Power più intelligente della stagione precedente.**

Ogni ciclo produttivo deve poter aumentare il patrimonio permanente di conoscenza dell’azienda. Il TPO non si limita a registrare attività: trasforma esperienza, osservazioni, risultati ed errori in conoscenza validata e riutilizzabile.

La conoscenza appartiene a Tower Power, non ai fornitori. Le osservazioni operative diventano conoscenza stabile soltanto attraverso confronto, validazione e approvazione.

## 3. Responsabilità del Register

Il Register VARIETÀ ha la responsabilità di:

- identificare la coltura generale;
- organizzare le CULTIVAR appartenenti a ciascuna VARIETÀ;
- associare ogni CULTIVAR ai suoi USI PRODUTTIVI senza duplicarne l’identità;
- custodire la conoscenza produttiva stabile riferita alla combinazione CULTIVAR × USO PRODUTTIVO;
- governare i Protocolli Standard e il loro versionamento;
- mantenere separati i Protocolli Sperimentali dagli standard vigenti;
- collegare gli USI PRODUTTIVI alle SEMENTI commerciali utilizzabili;
- distinguere la valutazione tecnica delle SEMENTI dalla conoscenza produttiva di Tower Power;
- preservare la relazione tra SEMENTI, LOTTI DI SEME e utilizzi produttivi;
- conservare lo storico e la genealogia del know-how senza cancellare entità dotate di tracciabilità.

## 4. Confini

### 4.1 Appartiene a VARIETÀ

Appartengono al perimetro del Register:

- l’identità generale della VARIETÀ;
- l’identità specifica della CULTIVAR;
- gli USI PRODUTTIVI associati alle CULTIVAR;
- la conoscenza tecnica stabile e validata per CULTIVAR × USO PRODUTTIVO;
- i Protocolli Standard e il loro versionamento;
- la separazione e la relazione controllata con i Protocolli Sperimentali;
- le SEMENTI come referenze commerciali;
- la valutazione contestuale delle SEMENTI;
- i LOTTI DI SEME come materiale fisico ricevuto;
- i principi di ciclo di vita, tracciabilità e conservazione dello storico.

### 4.2 Non appartiene a VARIETÀ

Non appartengono al Register:

- una trattazione botanica enciclopedica;
- un catalogo commerciale dei fornitori;
- le osservazioni di singole SEMINE, RACCOLTE o PROBLEMI;
- la progettazione completa di SEMINE o dei LOTTI produttivi;
- la progettazione completa del futuro dominio RICERCA & SVILUPPO;
- la progettazione della futura BASE DI CONOSCENZA trasversale;
- lo schema tecnico definitivo di campi, database o fogli;
- l’implementazione applicativa.

## 5. Modello concettuale

La gerarchia concettuale approvata è:

```text
VARIETÀ
└── CULTIVAR
    └── USO PRODUTTIVO
        └── SEMENTE
            └── LOTTO DI SEME
```

La conoscenza produttiva stabile è centrata sulla combinazione:

```text
CULTIVAR × USO PRODUTTIVO
```

La valutazione tecnica di una referenza sementiera è centrata sulla combinazione:

```text
SEMENTE × CULTIVAR × USO PRODUTTIVO
```

Ogni livello rappresenta un solo livello della realtà:

| Livello | Domanda a cui risponde |
|---|---|
| VARIETÀ | Di quale coltura generale stiamo parlando? |
| CULTIVAR | Quale identità specifica della coltura vogliamo produrre? |
| USO PRODUTTIVO | Che cosa vuole ottenere Tower Power da quella cultivar? |
| SEMENTE | Quale referenza sementiera commerciale utilizziamo? |
| LOTTO DI SEME | Quale materiale fisico specifico è stato acquistato e utilizzato? |

Le informazioni di livelli differenti non sono incorporate artificialmente in un’unica voce.

Esempio:

```text
VARIETÀ: Basilico
├── CULTIVAR: Genovese
│   ├── USO PRODUTTIVO: Microgreen
│   ├── USO PRODUTTIVO: Baby leaf
│   └── USO PRODUTTIVO: Pianta adulta
├── CULTIVAR: Thai
├── CULTIVAR: Greco
└── CULTIVAR: Limone
```

## 6. VARIETÀ

La VARIETÀ è l’identità produttiva generale della coltura. È unica nel proprio significato e può comprendere più CULTIVAR.

La VARIETÀ non viene duplicata per ogni CULTIVAR, USO PRODUTTIVO, fornitore, SEMENTE o LOTTO DI SEME. Il fornitore e la referenza commerciale non ne determinano l’identità.

Una VARIETÀ può sostenere molti usi attraverso le proprie CULTIVAR. Per esempio, il Coriandolo conserva una sola identità di VARIETÀ anche quando una CULTIVAR è destinata a Microgreen, Baby leaf, Pianta adulta, Fiore o Seme.

## 7. CULTIVAR

La CULTIVAR identifica la specifica identità della coltura che Tower Power vuole produrre. Ogni CULTIVAR appartiene a una VARIETÀ e può essere associata a più USI PRODUTTIVI.

La stessa CULTIVAR non viene duplicata per rappresentare usi differenti. Tempi, rese e altri parametri dipendenti dall’uso non sono collocati genericamente nella CULTIVAR, ma nella conoscenza relativa alla combinazione CULTIVAR × USO PRODUTTIVO.

Lo stato della CULTIVAR è indipendente dallo stato generale della VARIETÀ. La sospensione o dismissione di una CULTIVAR non comporta quella dell’intera VARIETÀ.

## 8. USO PRODUTTIVO

L’USO PRODUTTIVO descrive ciò che Tower Power vuole ottenere da una CULTIVAR. Può comprendere, tra gli altri, Microgreen, Baby leaf, Pianta adulta, Fiore e Seme, oltre a usi futuri.

L’USO PRODUTTIVO non crea una nuova identità di CULTIVAR. Una CULTIVAR può avere più USI PRODUTTIVI, ciascuno con la propria conoscenza tecnica, il proprio stato di validazione e, quando esiste, il proprio Protocollo Standard.

## 9. Conoscenza CULTIVAR × USO PRODUTTIVO

Il centro della conoscenza produttiva è la combinazione CULTIVAR × USO PRODUTTIVO. A questa combinazione appartengono:

- protocollo standard;
- standard qualitativo;
- tempi attesi;
- resa attesa;
- criteri di raccolta;
- criticità note;
- parametri produttivi;
- stato di validazione;
- conoscenza tecnica consolidata.

Questa conoscenza è patrimonio di Tower Power. Non appartiene genericamente alla sola VARIETÀ, non viene attribuita alla SEMENTE e non viene duplicata al cambiare del fornitore o della referenza commerciale.

## 10. Protocollo Standard

Per ogni combinazione CULTIVAR × USO PRODUTTIVO può esistere un Protocollo Standard ufficiale. Esso descrive come Tower Power coltiva una determinata CULTIVAR per uno specifico USO PRODUTTIVO.

Il Protocollo Standard:

- rappresenta il metodo produttivo ufficiale di Tower Power;
- deve essere seguito rigorosamente nella produzione ordinaria;
- contiene conoscenza validata;
- non appartiene al fornitore né alla singola SEMENTE;
- non viene duplicato per ogni referenza sementiera;
- rimane patrimonio di Tower Power quando cambia il fornitore;
- è versionato e conserva le versioni precedenti.

## 11. Protocollo Sperimentale

Il Protocollo Sperimentale è separato dal Protocollo Standard. Consente prove controllate senza mettere a rischio la produzione ordinaria e mantiene la sperimentazione distinta dalla produzione standard.

Un Protocollo Sperimentale può sostituire il Protocollo Standard soltanto dopo:

1. esecuzione delle prove;
2. raccolta dei risultati;
3. confronto;
4. validazione;
5. approvazione.

Uno standard non viene modificato sulla base di intuizioni o impressioni non verificate. Anche un esperimento fallito produce conoscenza utile e deve poter lasciare una traccia riutilizzabile.

Tower Power considera la ricerca una funzione permanente e il sistema deve supportare sperimentazioni controllate ricorrenti. La progettazione completa del futuro dominio RICERCA & SVILUPPO resta tuttavia fuori dal perimetro di questo documento.

## 12. Versionamento e genealogia

Il Protocollo Standard è versionato. Una nuova versione non sovrascrive né elimina la precedente.

Ogni versione deve poter indicare:

- identificativo o numero di versione;
- data di entrata in vigore;
- modifica apportata;
- motivazione;
- evidenze utilizzate;
- eventuale sperimentazione di origine;
- versione precedente;
- stato della versione.

Deve essere possibile ricostruire quale versione fosse valida in un determinato momento e quale sia stata utilizzata per una determinata produzione.

Il flusso approvato per l’origine di un nuovo standard è:

```text
Idea → Esperimento → Risultati → Validazione → Nuova versione del Protocollo Standard
```

Ogni modifica significativa deve rendere conoscibili:

- che cosa è cambiato;
- perché è cambiato;
- su quali evidenze si basa.

Il sistema conserva inoltre la genealogia del know-how. Un protocollo può derivare da una versione precedente, da un protocollo relativo a un’altra CULTIVAR, da una sperimentazione o da una combinazione di evidenze precedenti. La derivazione non implica duplicazione: deve essere possibile risalire alla conoscenza iniziale e comprenderne l’adattamento nel tempo.

## 13. SEMENTE

La SEMENTE rappresenta una specifica referenza commerciale acquistabile e associabile a un USO PRODUTTIVO di una CULTIVAR. Un USO PRODUTTIVO può essere associato a più SEMENTI.

La SEMENTE può comprendere informazioni commerciali e dichiarative quali:

- fornitore;
- marca;
- codice o referenza commerciale;
- formato;
- trattamento dichiarato;
- certificazioni dichiarate;
- informazioni di catalogo;
- disponibilità commerciale.

Il fornitore e la referenza commerciale non definiscono l’identità della VARIETÀ o della CULTIVAR. Gli ordini dei clienti riguardano il prodotto o la coltura richiesta, non il fornitore della semente; Tower Power sceglie la SEMENTE più adatta.

## 14. Valutazione della SEMENTE

La valutazione tecnica di una SEMENTE dipende dal suo impiego ed è quindi riferita alla combinazione SEMENTE × CULTIVAR × USO PRODUTTIVO.

La valutazione può comprendere:

- rating;
- germinazione;
- uniformità;
- vigore;
- resa;
- estetica;
- sapore;
- durata post-raccolta;
- affidabilità;
- raccomandazione;
- motivazione tecnica;
- data dell’ultima revisione.

Gli stati di raccomandazione distinguono almeno:

- raccomandata;
- utilizzabile;
- sconsigliata.

La valutazione della SEMENTE non duplica il Protocollo Standard. Il protocollo descrive come Tower Power produce; la valutazione descrive quanto una specifica SEMENTE è adatta a quella produzione.

Un’anomalia relativa a un singolo LOTTO DI SEME non compromette automaticamente la valutazione generale della SEMENTE senza evidenze adeguate.

## 15. LOTTO DI SEME

Il LOTTO DI SEME rappresenta il materiale fisico effettivamente ricevuto. Preserva la tracciabilità tra acquisto, disponibilità e utilizzo produttivo ed è distinto dalla SEMENTE, che rappresenta la referenza commerciale.

Un LOTTO DI SEME può comprendere:

- numero di lotto del produttore;
- data di acquisto o ricezione;
- scadenza;
- quantità iniziale;
- quantità residua;
- costo;
- documentazione;
- anomalie specifiche;
- collegamento alle SEMINE che lo hanno utilizzato.

I problemi specifici del lotto restano attribuiti al materiale fisico interessato finché evidenze adeguate non giustifichino una revisione della valutazione generale della SEMENTE.

## 16. Ciclo di vita

VARIETÀ e CULTIVAR dotate di storico non vengono cancellate. Devono poter assumere stati coerenti quali:

- ATTIVA;
- IN SPERIMENTAZIONE, quando applicabile;
- SOSPESA;
- DISMESSA.

Lo stato della CULTIVAR è indipendente da quello della VARIETÀ. La dismissione di una CULTIVAR non comporta la dismissione dell’intera VARIETÀ.

La sospensione e la dismissione preservano la tracciabilità e le relative motivazioni. Lo storico conserva:

- esperimenti;
- protocolli;
- sementi valutate;
- raccolti;
- motivazioni della sospensione o dismissione;
- conoscenza acquisita.

## 17. Separazione dalle osservazioni operative

In VARIETÀ vive la conoscenza tecnica stabile e validata. Le osservazioni relative a singoli eventi produttivi appartengono ai Register operativi appropriati, tra cui SEMINE, RACCOLTE, PROBLEMI ed eventuali registrazioni sperimentali future.

Un problema osservato durante una singola SEMINA non diventa automaticamente una regola generale di VARIETÀ. La conoscenza generale emerge attraverso confronto, validazione e approvazione.

## 18. Relazioni con gli altri Register

- **SEMINE:** registra gli eventi di semina. Le osservazioni della singola SEMINA restano operative.
- **RACCOLTE:** registra risultati e osservazioni dei singoli raccolti. Tali dati possono fornire evidenze, ma non costituiscono da soli conoscenza stabile di VARIETÀ.
- **PROBLEMI:** registra le anomalie operative nel loro contesto. Un problema diventa conoscenza generale soltanto dopo il processo di validazione e approvazione.
- **LOTTI produttivi:** restano un dominio distinto dai LOTTI DI SEME; la loro progettazione completa non appartiene a questo documento.
- **RICERCA & SVILUPPO futuro:** la progettazione del dominio RICERCA & SVILUPPO è rinviata a una futura Architecture Review.
- **BASE DI CONOSCENZA futura:** potrà ospitare conoscenza trasversale applicabile a più varietà, cultivar, famiglie botaniche, sementi o sistemi produttivi. È qui riconosciuta esclusivamente come confine architetturale e possibile dipendenza futura.

## 19. Invarianti architetturali

1. Una VARIETÀ identifica una sola coltura generale e non viene duplicata per CULTIVAR, uso, fornitore o semente.
2. Una CULTIVAR identifica una sola identità specifica e non viene duplicata per ogni USO PRODUTTIVO.
3. Ogni CULTIVAR può essere associata a più USI PRODUTTIVI e ogni USO PRODUTTIVO può essere associato a più SEMENTI.
4. La conoscenza tecnica stabile dipendente dall’uso appartiene alla combinazione CULTIVAR × USO PRODUTTIVO.
5. Il Protocollo Standard appartiene a Tower Power e non al fornitore o alla SEMENTE.
6. Il Protocollo Standard non viene duplicato per ogni SEMENTE.
7. La valutazione tecnica della SEMENTE appartiene alla combinazione SEMENTE × CULTIVAR × USO PRODUTTIVO e non duplica il protocollo.
8. SEMENTE e LOTTO DI SEME rappresentano livelli distinti: referenza commerciale e materiale fisico.
9. Un problema di un singolo LOTTO DI SEME non modifica automaticamente la valutazione generale della SEMENTE.
10. Il Protocollo Sperimentale resta separato dal Protocollo Standard finché non completa prove, raccolta dei risultati, confronto, validazione e approvazione.
11. Ogni versione del Protocollo Standard conserva le versioni precedenti e la propria origine documentata.
12. Deve essere ricostruibile il protocollo valido in un dato momento e quello usato in una determinata produzione.
13. Le osservazioni operative non diventano conoscenza stabile senza validazione e approvazione.
14. Le entità con uno storico non vengono cancellate: vengono sospese o dismesse preservandone la tracciabilità.
15. La conoscenza viene registrata una sola volta nel livello corretto.

## 20. Aree esplicitamente rinviate

Restano esplicitamente rinviate e non sono progettate in questo documento:

- lo schema tecnico definitivo dei campi;
- database, fogli e implementazioni applicative;
- la progettazione completa di SEMINE;
- la progettazione completa dei LOTTI produttivi;
- il futuro dominio RICERCA & SVILUPPO;
- la futura BASE DI CONOSCENZA trasversale;
- eventuali nuovi Register o strutture non ancora approvati.

## 21. Stato di Freeze Review

Il presente documento è in stato:

**ARCHITECTURE FROZEN v1.0**

Il documento è dichiarato **ARCHITECTURE FROZEN v1.0** a seguito di:

1. lettura del documento;
2. analisi del diff;
3. Consistency Review;
4. approvazione esplicita.

La Freeze Review è stata completata con approvazione esplicita.
