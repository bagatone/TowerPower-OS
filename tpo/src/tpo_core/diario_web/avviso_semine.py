"""AVVISO SUL TELEFONO delle sessioni di semina (17/10/2026, richiesta di Matteo): mercoledi e domenica mattina arriva una
notifica con COSA seminare, il TOTALE PER VARIETA' e il totale complessivo. Il "per chi" (clienti) NON e' nel messaggio:
passa da un servizio esterno (ntfy), quindi resta nella schermata "Semine" del diario, che si apre toccando la notifica.

Sola lettura sul database: legge il piano con `sessioni_semina.piano` (lo stesso della schermata Semine). L'unica cosa che
"scrive" e' la notifica verso ntfy. Mai scritture sul database (guardia D del freeze OPERATIONAL_WEB_ADAPTER).

Configurazione (variabili d'ambiente, mai nel repository):
  NTFY_TOPIC   nome del canale, lungo e segreto: chi lo conosce legge gli avvisi (obbligatorio per inviare)
  NTFY_SERVER  default https://ntfy.sh
  DIARIO_URL   indirizzo del diario, aperto toccando la notifica (default https://tpo-diario.onrender.com)

Quando parte: solo mercoledi e domenica (ora delle Canarie) tra le 07:00 e le 10:00; una seconda chiamata nella stessa
mattina non rimanda l'avviso (si guarda nella cache di ntfy se e' gia' stato mandato). Cosi' un orario in UTC con due
tentativi (ora legale / solare) o un ritardo del servizio che lo lancia non producono doppioni ne' buchi.
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Callable
from zoneinfo import ZoneInfo

from ..infrastructure.postgresql.settings import PostgreSQLSettings
from . import sessioni_semina as ss

TZ = ZoneInfo("Atlantic/Canary")
NTFY_DEFAULT = "https://ntfy.sh"
DIARIO_URL_DEFAULT = "https://tpo-diario.onrender.com"
ORA_DA = 7
ORA_A = 10                                  # esclusa
TIMEOUT = 15

Opener = Callable[..., object]


class AvvisoNonPossibile(Exception):
    """Configurazione mancante o servizio di notifica non raggiungibile: il messaggio e' leggibile."""


@dataclass(frozen=True)
class Avviso:
    titolo: str
    corpo: str
    priorita: int                           # 1..5 come ntfy (3 = normale)
    tag: str                                # es. semine-2026-10-18: serve a non rimandare lo stesso avviso


def _n(value) -> str:
    """Quantita' all'italiana: 4.50 -> "4,5"."""
    text = format(Decimal(value).normalize(), "f")
    return text.replace(".", ",")


def _breve(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}"


def _riga_varieta(v: ss.VarietaDaSeminare) -> str:
    return f"{v.varieta} {_n(v.quantita)} {v.unita}"


def _totale(sessione: ss.Sessione) -> str:
    return ", ".join(f"{_n(q)} {u}" for u, q in sessione.quantita_per_unita.items())


def componi(piano: ss.PianoSessioni) -> Avviso:
    """Piano -> testo della notifica. Funzione pura. Nessun nome di cliente."""
    sessioni = list(piano.sessioni)
    oggi = next((s for s in sessioni if s.data == piano.oggi), None)
    prossime = [s for s in sessioni if s.data > piano.oggi]
    nome_oggi = ss.NOMI_GIORNO[piano.oggi.weekday()]
    righe: list[str] = []
    if oggi is not None:
        titolo = f"Semina di {nome_oggi} {_breve(oggi.data)}: {_totale(oggi)}"
        righe += [_riga_varieta(v) for v in oggi.varieta]
        priorita = 4
    else:
        titolo = f"{nome_oggi.capitalize()} {_breve(piano.oggi)}: nessuna semina da fare"
        priorita = 3
    if prossime:
        p = prossime[0]
        righe.append(f"Prossima, {p.nome_giorno} {_breve(p.data)}: {', '.join(_riga_varieta(v) for v in p.varieta)}")
    extra = []
    if piano.da_verificare:
        extra.append(f"da verificare {len(piano.da_verificare)}")
    if piano.scaduti:
        extra.append(f"ordini scaduti {len(piano.scaduti)}")
    if extra:
        righe.append("Attenzione: " + ", ".join(extra) + ".")
    righe.append("Tocca per vedere per chi.")
    return Avviso(titolo, "\n".join(righe), priorita, f"semine-{piano.oggi.isoformat()}")


def _config() -> tuple[str, str, str]:
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        raise AvvisoNonPossibile("NTFY_TOPIC non impostata: senza il nome del canale non so dove mandare l'avviso.")
    server = os.environ.get("NTFY_SERVER", NTFY_DEFAULT).strip().rstrip("/") or NTFY_DEFAULT
    diario = os.environ.get("DIARIO_URL", DIARIO_URL_DEFAULT).strip().rstrip("/") or DIARIO_URL_DEFAULT
    return topic, server, diario


def gia_inviato(server: str, topic: str, tag: str, opener: Opener = urllib.request.urlopen) -> bool:
    """Guarda nella cache di ntfy (ultime 12 ore) se un avviso con questo tag e' gia' arrivato. Se non si riesce a
    controllare risponde False: meglio un doppione di un avviso mancato."""
    try:
        with opener(f"{server}/{topic}/json?poll=1&since=12h", timeout=TIMEOUT) as risposta:
            for riga in risposta.read().decode("utf-8").splitlines():
                try:
                    if tag in (json.loads(riga).get("tags") or []):
                        return True
                except ValueError:
                    continue
    except Exception:  # noqa: BLE001 -- controllo best effort
        return False
    return False


def invia(avviso: Avviso, opener: Opener = urllib.request.urlopen) -> None:
    topic, server, diario = _config()
    corpo = {"topic": topic, "title": avviso.titolo, "message": avviso.corpo, "priority": avviso.priorita,
             "tags": [avviso.tag, "seedling"], "click": f"{diario}/#semine"}
    richiesta = urllib.request.Request(
        server, data=json.dumps(corpo).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with opener(richiesta, timeout=TIMEOUT) as risposta:
            if getattr(risposta, "status", 200) >= 300:
                raise AvvisoNonPossibile(f"Il servizio di notifica ha risposto {risposta.status}.")
    except AvvisoNonPossibile:
        raise
    except Exception as exc:  # noqa: BLE001 -- mostrato, mai un crash silenzioso
        raise AvvisoNonPossibile(f"Avviso non inviato: {exc}") from exc


def finestra_ok(ora: datetime) -> bool:
    return ora.isoweekday() in ss.GIORNI_DEFAULT and ORA_DA <= ora.hour < ORA_A


def esegui(settings: PostgreSQLSettings, ora: datetime | None = None, *, anteprima: bool = False, prova: bool = False,
           forza: bool = False, opener: Opener = urllib.request.urlopen) -> dict:
    """Prepara e (se non e' anteprima) manda l'avviso. Ritorna sempre un dizionario leggibile, mai un'eccezione per
    "fuori orario" o "gia' mandato"."""
    ora = (ora or datetime.now(TZ)).astimezone(TZ)
    if prova:
        avviso = Avviso("Prova avviso semine", "Se leggi questo, le notifiche del diario arrivano sul telefono.", 3,
                        "semine-prova")
        if not anteprima:
            invia(avviso, opener)
        return {"inviato": not anteprima, "motivo": "prova", "titolo": avviso.titolo, "messaggio": avviso.corpo}
    if not forza and not finestra_ok(ora):
        return {"inviato": False, "motivo": "Fuori orario: l'avviso parte solo mercoledi e domenica tra le 07:00 e le 10:00 "
                                            "(ora delle Canarie). Per provare: forza=1.", "titolo": None, "messaggio": None}
    avviso = componi(ss.piano(settings, oggi=ora.date()))
    base = {"titolo": avviso.titolo, "messaggio": avviso.corpo}
    if anteprima:
        return {**base, "inviato": False, "motivo": "anteprima"}
    topic, server, _ = _config()
    if not forza and gia_inviato(server, topic, avviso.tag, opener):
        return {**base, "inviato": False, "motivo": "Avviso di oggi gia' inviato."}
    invia(avviso, opener)
    return {**base, "inviato": True, "motivo": "inviato"}
