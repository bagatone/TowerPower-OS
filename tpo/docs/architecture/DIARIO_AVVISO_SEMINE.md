# Avviso semine sul telefono (17/10/2026)

Richiesta di Matteo: ogni **mercoledi e domenica mattina** una notifica sul telefono con cosa seminare, il **totale per
varieta'** e il totale complessivo. Il "per chi" (clienti) resta nella schermata **Semine** del diario (il messaggio ha il
link): i nomi dei clienti non passano dal servizio esterno.

## Come funziona
1. **GitHub Actions** (workflow `tpo/deploy/github/avviso-semine.yml`, copiato in `.github/workflows/` sul ramo `main`; gratuito)
   chiama alle 06:35 e 07:35 UTC `POST {DIARIO_URL}/api/avviso-semine` con la password del diario. Sveglia il servizio Render
   (che dorme) con nuovi tentativi.
2. Il diario (`diario_web/avviso_semine.py`) legge il piano con `sessioni_semina.piano` (sola lettura, nessuna scrittura sul
   database) e compone il messaggio. Parte solo mercoledi/domenica (ora delle Canarie).
3. Lo manda a **Telegram** (canale preferito, se `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` sono impostati) oppure a **ntfy**
   (`NTFY_TOPIC`).
   - Telegram non ha una cache da consultare: finestra **07:00-08:00** (Canarie), cosi' dei due tentativi in UTC (ora legale /
     solare) ne cade uno solo e non ci sono doppioni.
   - ntfy: finestra 07:00-10:00 e controllo nella cache di ntfy (12 ore) che l'avviso di oggi non sia gia' arrivato.
     Nota: ntfy.sh puo' rifiutare l'IP condiviso di Render con **HTTP 429**: per questo e' il canale di riserva.

Esempio:  `Semina di domenica 18/10: 4,5 SET` / `Afila 3 SET` / `Cilantro 1 SET` / `Rábano 0,5 SET` /
`Prossima, mercoledi 21/10: Mizuna 2 SET` / `Tocca per vedere per chi.` / link al diario.

## Messa in funzione con Telegram (una volta)
1. **Bot**: in Telegram cerca **@BotFather** > `/newbot` > scegli un nome e un username che finisce con `bot`. BotFather risponde
   con il **token** (tipo `123456:ABC...`): e' una password, non va scritto in chat ne' nel repository.
2. **Chat**: apri il tuo nuovo bot e scrivigli "ciao" (il bot non puo' scriverti se prima non gli scrivi tu).
3. **Chat id**: nel browser apri `https://api.telegram.org/bot<TOKEN>/getUpdates` (al posto di `<TOKEN>` il token). Cerca
   `"chat":{"id":NUMERO` e copia il NUMERO (e' il `TELEGRAM_CHAT_ID`; per un gruppo e' negativo).
4. **Render** (servizio `tpo-diario` > Environment): aggiungi `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`, salva (riparte da solo).
5. **GitHub** (Settings > Secrets and variables > Actions): `DIARIO_URL` e `DIARIO_PASSWORD` (gia' fatti).
6. **Prova**: GitHub > Actions > "Avviso semine" > Run workflow (prova = true). Il messaggio "Prova avviso semine" arriva su Telegram.
   Da terminale: `curl -u x:PASSWORD -X POST "https://tpo-diario.onrender.com/api/avviso-semine?prova=1"`.
   Anteprima del messaggio vero senza mandarlo: `...?anteprima=1`. Forzare l'invio fuori orario: `...?forza=1`.

## Alternativa ntfy (se Telegram non e' impostato)
App **ntfy** sul telefono, iscrizione a un canale con nome lungo e segreto, `NTFY_TOPIC` = quel nome su Render
(`NTFY_SERVER` e `DIARIO_URL` hanno gia' un valore predefinito).

## Limiti dichiarati
- Telegram e ntfy sono servizi di terzi: il messaggio contiene solo varieta' e SET, mai clienti ne' codici ordine.
- Gli orari dei workflow di GitHub possono slittare di qualche minuto: con Telegram, se **entrambi** i tentativi cadono dopo le 08:00
  l'avviso non parte (si vede dal log del workflow "Fuori orario"; si puo' forzare con `?forza=1`).
- Se il servizio Render non si sveglia o la password e' sbagliata, il workflow fallisce e GitHub lo segnala nella pagina Actions.
