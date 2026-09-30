---
stato: OWNER DECISION CONFERMATE (implementazione in corso)
data: 2026-09-29
aggiornato: 2026-09-30
autore: sessione Claude (progetto "TPO system")
---

# Rendiconto Mattutino — Proposta

## 0. Perché questo documento esiste

Richiesta diretta di Matteo, 29/9/2026, verbatim (sintesi): il sistema
dovrebbe salutarlo la mattina con un messaggio del tipo *"Buongiorno
Matteo, oggi consegniamo a Jaira: 1 Afila (lotto AFI-1909-A), 0.5
Cilantro (lotto ...), 0.5 Rábano (lotto ...). Confermi? Procedo con
fattura o bolla di consegna?"* più l'elenco di cosa seminare oggi (tot
SET di Afila/Cilantro/Albahaca) — **non** un terminale dove lui incolla
comandi bash e aspetta ore per poi sentirsi chiedere "a che ora è stata
piantata questa semina?" per un evento che ha già vissuto di persona.

Non è una lamentela generica: è la richiesta di fondo presente fin dai
primi Fatti di `scoperta-tpo-roadmap-2026-09.md` (Fatto 19 in poi), mai
del tutto risolta. Questo documento la scompone in un progetto concreto,
nello stesso stile delle Freeze/Proposte già usate in questo repository
(situazione reale → gap → Owner Decision → modello → guardie → fuori
scope → prossimo passo).

## 1. Cosa esiste già (verificato, non da costruire da zero)

Ogni pezzo di questa funzione esiste già, separatamente:

- **"Cosa seminare"**: `tpo.righe_piano_semina` (boundary
  `pianificazione_semina_lettura`, Fatto 19) — già calcola a ritroso dai
  giorni di germinazione/luce/crescita del protocollo quanto seminare e
  quando, aggiornato ogni giorno alle 06:30 dal Production Planning
  Engine (ora che il blocco TCC/sandbox è risolto, Fatto 31).
- **"Cosa consegnare oggi"**: `tpo.righe_ordine`/`tpo.ordini` (boundary
  `fornitura_ordini_consegne_lettura`) hanno già le righe coperte da
  produzione/stock, con la data di consegna prevista.
- **"Con quale lotto"**: `tpo.stock`/`tpo.movimenti_magazzino`
  (boundary `magazzino_lettura`) hanno già la tracciabilità per
  VARIETA+unità di misura, collegata a `RAC-.../SEM-...` a monte.
- **"Genera fattura o bolla"**: `tpo delivery fulfil` +
  `tpo fattura emetti` sono comandi governati già esistenti e testati
  (usati per le prime consegne reali, Fatto 23/26).
- **Canale conversazionale già in produzione**: il diario
  (`tpo-diario.onrender.com`, Fatto 28/29) ha già hosting su internet,
  autenticazione, un attore Claude che legge lo stato reale e propone
  prima di scrivere — stesso principio che serve qui.

**Quello che manca non è nessuno di questi pezzi singolarmente — è
l'unione proattiva**: oggi ognuno di questi è una pagina/comando che
Matteo deve ricordarsi di aprire/lanciare. Nessuno lo cerca e lo porta a
lui la mattina.

## 2. Owner Decision da prendere (aperte, non ancora chieste a Matteo)

1. **Canale di consegna del rendiconto**: messaggio nel diario stesso
   (pagina che si apre già "pronta" la mattina), notifica push/email, o
   entrambi? (Il diario oggi non ha alcun canale attivo — Fatto 19 lo
   dichiarava esplicitamente fuori scope, va riconsiderato qui.)
2. **Cosa succede se manca un dato** (es. lotto non ancora tracciato,
   stock insufficiente per una riga): il rendiconto deve segnalarlo
   esplicitamente come riga "da chiarire" (mai indovinare/saltare in
   silenzio) — coerente con ogni altra parte del sistema, ma va deciso
   il formato della segnalazione.
3. **Fattura o bolla di consegna, chi decide**: il messaggio proposto da
   Matteo lascia la scelta a lui ogni volta ("cosa preferisci?") — va
   confermato se è sempre così o se può diventare una preferenza di
   default per cliente.
4. **Perimetro Fase 1**: solo lettura + proposta (rendiconto mostra,
   Matteo conferma a voce/testo nel diario, il sistema esegue
   `delivery fulfil`/`fattura emetti`/`semina commission` già esistenti)
   — nessuna scrittura senza conferma esplicita, stesso principio già
   approvato per il diario (D4-bis, Fatto 28).

## 2-bis. Risposte di Matteo (30/9/2026)

1. **Canale**: solo il diario — nessuna pagina/notifica nuova da
   costruire, il rendiconto si apre già pronto come messaggio del
   giorno quando Matteo apre `tpo-diario.onrender.com`.
2. **Dati mancanti**: ogni riga con un dato non risolvibile con
   certezza (lotto non tracciato, stock insufficiente) compare **in
   cima al rendiconto**, marcata esplicitamente "da chiarire",
   separata dalle righe pronte da confermare — mai mescolata, mai
   indovinata.
3. **Fattura vs bolla**: il rendiconto **chiede sempre**, riga per
   riga, esattamente come nella richiesta originale di Matteo — nessun
   default per cliente in Fase 1.
4. **Perimetro**: confermato — solo lettura + proposta, nessuna
   scrittura senza conferma esplicita di Matteo.

**Gap scoperto in fase di disegno, non coperto dalle 4 Owner Decision
originali**: il diario oggi (Fatto 28, D4-bis) è autorizzato a scrivere
**solo** `semina commission`/`semina transition`. Il Rendiconto
Mattutino, per la parte "consegne" della OD4, richiede che il diario
esegua anche `delivery fulfil` e `fattura emetti` — due nuovi comandi
di scrittura mai autorizzati per il diario finora. Serve una OD5
esplicita (stesso principio del D4-bis originale: nessun nuovo
percorso di scrittura applicativa, solo l'invocazione governata di
comandi già testati, ma il perimetro del diario va allargato di
proposito, non silenziosamente).

**OD5, risposta di Matteo (30/9/2026): sì, allarga il perimetro.** Il
diario potrà eseguire, dopo conferma esplicita riga per riga, anche
`delivery fulfil` e `fattura emetti` — stesso principio già in vigore
per `semina commission`/`semina transition` (D4-bis): nessun nuovo
percorso di scrittura applicativa, solo invocazione governata di
comandi già testati, sempre con proposta mostrata prima e mai
un'esecuzione senza conferma.

## 3. Modello proposto (bozza, da affinare con le risposte sopra)

Un nuovo servizio (`rendiconto_mattutino`, riuso totale dei boundary di
lettura esistenti, nessuna nuova tabella richiesta per la Fase 1):

1. Alle 07:00 Atlantic/Canary (dopo che Scheduling 06:00 e Production
   Planning 06:30 hanno già girato), un nuovo LaunchAgent/job compone il
   rendiconto del giorno:
   - righe ordine con consegna prevista oggi, con lotto/stock già
     risolto per ciascuna (o segnalazione esplicita se manca);
   - righe di "Da seminare" con data prevista oggi/scaduta.
2. Il rendiconto viene reso disponibile nel diario come messaggio
   pronto ad aprirsi (Owner Decision 1 decide se anche notificato
   attivamente).
3. Matteo conferma (tutto insieme o riga per riga — da decidere): il
   sistema esegue i comandi già esistenti (`delivery fulfil`,
   `fattura emetti` o generazione bolla, `semina commission` per le
   nuove semine) — mai un percorso di scrittura nuovo, sempre quelli già
   testati.

## 4. Guardie (non negoziabili, stesso principio di tutto il resto del sistema)

- Mai un dato inventato: se un lotto/stock non è risolvibile con
  certezza, il rendiconto lo segnala come riga aperta, non tenta una
  scelta.
- Nessuna scrittura (fattura, consegna, semina) senza conferma esplicita
  di Matteo — stessa garanzia già in vigore per il diario.
- Riuso assoluto dei comandi/boundary già governati e testati — questo
  documento non introduce nessun nuovo percorso di scrittura.

## 5. Esplicitamente fuori scope (Fase 1)

- Raccolta/carico automatico (resta manuale, dichiarazione reale di
  quanto pesato — Owner Decision D11/D12 già congelata, invariata).
- Bollette/fatturazione elettronica verso l'Agenzia Tributaria (se mai
  richiesta, è un progetto a sé).
- Rendiconto per varietà senza ancora un protocollo/lotto commissionato
  (es. Basilico/Rucola oggi) — quelle righe compariranno come "da
  seminare" solo una volta chiuso il gap già noto (roadmap, punto 13).

## 6. Prossimo passo

**Le 4 Owner Decision del §2 sono state risposte da Matteo il
30/9/2026 (vedi §2-bis).** Implementazione in corso, in due parti
indipendenti:

- **Parte A (sbloccata, nessuna nuova OD necessaria)**: il motore di
  composizione read-only (righe da seminare oggi + righe di consegna
  oggi con lotto/stock risolto, righe "da chiarire" separate in cima)
  e la sua esposizione nel diario come rendiconto del giorno. Riusa
  solo boundary di lettura già esistenti e testati
  (`pianificazione_semina_lettura`, `fornitura_ordini_consegne_lettura`,
  `magazzino_lettura`), nessuna scrittura.
- **Parte B (sbloccata il 30/9/2026, OD5)**: l'esecuzione guidata da
  conferma di `delivery fulfil`/`fattura emetti` dal diario stesso, per
  chiudere il ciclo "confermi? procedo con fattura o bolla" senza dover
  tornare al terminale.
