# Diario: promemoria degli stadi e controllo anomalie (19/10/2026)

Modulo `src/tpo_core/diario_web/controlli.py`, rotta `GET /api/controlli`, sezione nella schermata Oggi e due righe in piu'
nell'avviso del mattino. **Sola lettura**: connessione `read_only`, nessuna scrittura, nessuno stato cambia da solo.

## Promemoria (dal protocollo della semina)
- AVVIATA/GERMINAZIONE: passa a luce a `data_avvio + germinazione_giorni`.
- LUCE/CRESCITA (stesso processo): pronta a `data del passaggio a luce + crescita_luce_giorni` (se manca l'evento di
  passaggio si usa avvio + germinazione).
- Si mostrano "oggi", "in ritardo" (fino a 3 giorni per la luce, 5 per la raccolta) e "domani".
- Sono previsioni: Matteo raccoglie spesso prima, conta lo stato fisico che dichiara lui.

## Da controllare
- Semina ferma: oltre i limiti sopra la data prevista e' passata (stato probabilmente non aggiornato).
- Clienti con nome molto simile (somiglianza >= 0,8, senza accenti/maiuscole), con avviso se hanno entrambi un programma
  attivo (rischio ordini doppi: caso Salvaje/Selvaje).
- Lotto di seme usato negli ultimi 30 giorni che basta per meno di 10 SET (residuo a sistema / grammi per SET).

## Avviso del mattino
`avviso_semine.componi(piano, controllo)` aggiunge, prima di "Tocca per vedere per chi.", le righe
"Passano a luce: ...", "Pronte da raccogliere: ..." (oggi + in ritardo) e "Da controllare: N (vedi Oggi).".
Nessun nome di cliente. Se il controllo fallisce l'avviso parte lo stesso senza queste righe.

## Test
`tests/diario_web/test_controlli.py`, `tests/infrastructure/postgresql/test_diario_controlli.py`,
`tests/diario_web/test_avviso_semine.py` (righe extra).

## Registrare un cambio di stadio dal diario (19/10/2026, opzione 1 della roadmap, prima parte)
Ogni riga del Promemoria (e le semine "ferme" in Da controllare) ha un bottone **Registra…**: si sceglie il giorno
(oggi / ieri / l'altro ieri / altro giorno) ed eventualmente l'ora, si vede la proposta esatta, e solo con
**Conferma ed esegui** parte il comando governato `semina transition` (lo stesso di `2026-10-05_passa_a_luce.py`).
- Rotta `POST /api/stadio/prepara` (non scrive) + `POST /api/conferma` (esegue). Stessi vincoli D2/D3 del freeze:
  nessuna logica di dominio nuova, attore fisso, tracciamento in `audit_eventi`.
- Istanti: oggi senza ora = adesso; giorno passato senza ora = 12:00 (orario non osservato, detto nell'anteprima);
  mai nel futuro; mai prima dell'avvio o dell'ultimo passaggio registrato (messaggio col limite). Fuso Atlantic/Canary
  con ora legale. Dalla AVVIATA la GERMINAZIONE e' amministrativa, alla data di avvio (come negli script a mano).
  Passi multipli (es. luce -> pronta passa da CRESCITA): a un minuto l'uno dall'altro, l'ultimo all'istante dichiarato.
- Tutti gli istanti vengono controllati PRIMA di scrivere qualunque passo; il motivo registrato riporta data/ora dichiarata.
- Per ora solo i passaggi a LUCE e PRONTA_ALLA_RACCOLTA. Restano da fare: nuova semina con data/ora, chiusura semina,
  consegne e prove omaggio (seconde parti dell'opzione 1).
- Test: `tests/diario_web/test_stadio_con_data.py`, `tests/infrastructure/postgresql/test_diario_controlli.py`.
