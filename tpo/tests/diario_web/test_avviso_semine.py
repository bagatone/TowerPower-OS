"""Avviso sul telefono delle sessioni di semina (17/10/2026). Nessun database, nessuna rete: il piano e ntfy sono finti.
Si verifica il testo (totale per varieta', nessun nome di cliente), il giorno/ora, il non-doppione e gli errori leggibili."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from src.tpo_core.diario_web import app as app_module, avviso_semine as av, sessioni_semina as ss

AUTH = ("matteo", "segreta")
TZ = ZoneInfo("Atlantic/Canary")
DOMENICA = date(2026, 10, 18)
CLIENTI = ("Abaluus", "El Gringo", "Hotel Duna Blanca", "Sushi Tefia")


def _riga(i, varieta, cliente, quantita, ideale, consegna, grammi="30"):
    return ss.RigaSemina(f"RPS-{i}", varieta, cliente, f"ORD-{i:06d}", consegna, "PIANIFICATA", Decimal(quantita), "SET",
                         Decimal(grammi), ideale, consegna)


RIGHE = [
    _riga(1, "Afila", "Abaluus", "1", date(2026, 10, 18), date(2026, 10, 28)),
    _riga(2, "Afila", "El Gringo", "2", date(2026, 10, 18), date(2026, 10, 28)),
    _riga(3, "Cilantro", "Abaluus", "1", date(2026, 10, 19), date(2026, 10, 30)),
    _riga(4, "Rábano", "Hotel Duna Blanca", "0.5", date(2026, 10, 20), date(2026, 10, 29)),
    _riga(5, "Mizuna", "Sushi Tefia", "2", date(2026, 10, 21), date(2026, 10, 31)),
]


def _piano(righe=RIGHE, oggi=DOMENICA):
    return ss.assegna(list(righe), oggi, ss.GIORNI_DEFAULT, 2)


def test_il_testo_ha_il_totale_per_varieta_e_complessivo_senza_clienti() -> None:
    a = av.componi(_piano())
    assert a.titolo == "Semina di domenica 18/10: 4,5 SET"
    righe = a.corpo.splitlines()
    assert righe[:3] == ["Afila 3 SET", "Cilantro 1 SET", "Rábano 0,5 SET"]
    assert "Prossima, mercoledi 21/10: Mizuna 2 SET" in righe
    assert righe[-1] == "Tocca per vedere per chi."
    assert a.priorita == 4 and a.tag == "semine-2026-10-18"
    testo = a.titolo + a.corpo
    assert not any(cliente in testo for cliente in CLIENTI)      # i clienti non passano dal servizio esterno
    assert "ORD-" not in testo


def test_senza_semine_lo_dice_e_non_urla() -> None:
    a = av.componi(_piano([]))
    assert a.titolo == "Domenica 18/10: nessuna semina da fare" and a.priorita == 3
    assert a.corpo == "Tocca per vedere per chi."


def test_segnala_ordini_da_verificare_e_scaduti_senza_nominarli() -> None:
    o = ss.OrdineDaVerificare("ORD-000099", "Splash", date(2026, 10, 10), 0, ("Afila 1 SET",), "APERTO")
    p = replace(_piano(), scaduti=(o, o), da_verificare=(o,))
    corpo = av.componi(p).corpo
    assert "Attenzione: da verificare 1, ordini scaduti 2." in corpo and "Splash" not in corpo


@pytest.mark.parametrize("quando,atteso", [
    (datetime(2026, 10, 18, 7, 0, tzinfo=TZ), True),      # domenica
    (datetime(2026, 10, 21, 9, 59, tzinfo=TZ), True),     # mercoledi
    (datetime(2026, 10, 18, 6, 59, tzinfo=TZ), False),
    (datetime(2026, 10, 18, 10, 0, tzinfo=TZ), False),
    (datetime(2026, 10, 19, 8, 0, tzinfo=TZ), False),     # lunedi
])
def test_finestra_mercoledi_e_domenica_mattina(quando, atteso) -> None:
    assert av.finestra_ok(quando) is atteso


class _Risposta:
    def __init__(self, testo="", status=200):
        self._testo, self.status = testo, status

    def read(self):
        return self._testo.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Ntfy:
    """ntfy finto: GET = cache degli ultimi messaggi, POST = pubblicazione."""

    def __init__(self, cache=""):
        self.cache, self.inviati, self.letture, self.stato = cache, [], [], 200

    def __call__(self, richiesta, timeout=None):
        if isinstance(richiesta, str):
            self.letture.append(richiesta)
            return _Risposta(self.cache)
        self.inviati.append((richiesta.full_url, richiesta.get_method(), json.loads(richiesta.data.decode("utf-8"))))
        return _Risposta("", self.stato)


@pytest.fixture
def ambiente(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "canale-segreto-xyz")
    monkeypatch.delenv("NTFY_SERVER", raising=False)
    monkeypatch.delenv("DIARIO_URL", raising=False)
    visti = []

    def finto_piano(settings, oggi=None, **kw):
        visti.append(oggi)
        return _piano(oggi=oggi)

    monkeypatch.setattr(ss, "piano", finto_piano)
    return visti


DOMENICA_7_30 = datetime(2026, 10, 18, 7, 30, tzinfo=TZ)


def test_invia_il_messaggio_giusto_a_ntfy(ambiente) -> None:
    ntfy = _Ntfy()
    esito = av.esegui(object(), DOMENICA_7_30, opener=ntfy)
    assert esito["inviato"] is True and esito["titolo"] == "Semina di domenica 18/10: 4,5 SET"
    (url, metodo, corpo), = ntfy.inviati
    assert url == "https://ntfy.sh" and metodo == "POST"          # il canale e' nel corpo, non nell'indirizzo
    assert corpo["topic"] == "canale-segreto-xyz" and corpo["priority"] == 4
    assert corpo["click"] == "https://tpo-diario.onrender.com/#semine"
    assert "semine-2026-10-18" in corpo["tags"] and "Afila 3 SET" in corpo["message"]
    assert ambiente == [date(2026, 10, 18)]


def test_non_rimanda_lo_stesso_avviso_due_volte(ambiente) -> None:
    gia = json.dumps({"event": "message", "tags": ["semine-2026-10-18", "seedling"]})
    ntfy = _Ntfy(cache="\n".join(["non json", gia]))
    esito = av.esegui(object(), DOMENICA_7_30, opener=ntfy)
    assert esito["inviato"] is False and "gia' inviato" in esito["motivo"] and ntfy.inviati == []
    altro_giorno = _Ntfy(cache=json.dumps({"tags": ["semine-2026-10-14"]}))
    assert av.esegui(object(), DOMENICA_7_30, opener=altro_giorno)["inviato"] is True


def test_se_non_riesce_a_controllare_la_cache_manda_comunque(ambiente) -> None:
    class Rotto(_Ntfy):
        def __call__(self, richiesta, timeout=None):
            if isinstance(richiesta, str):
                raise OSError("rete")
            return super().__call__(richiesta, timeout)

    ntfy = Rotto()
    assert av.esegui(object(), DOMENICA_7_30, opener=ntfy)["inviato"] is True and len(ntfy.inviati) == 1


def test_fuori_giorno_o_ora_non_legge_il_database_e_non_invia(ambiente) -> None:
    ntfy = _Ntfy()
    lunedi = datetime(2026, 10, 19, 7, 30, tzinfo=TZ)
    esito = av.esegui(object(), lunedi, opener=ntfy)
    assert esito["inviato"] is False and "Fuori orario" in esito["motivo"]
    assert ntfy.inviati == [] and ntfy.letture == [] and ambiente == []
    assert av.esegui(object(), lunedi, forza=True, opener=ntfy)["inviato"] is True     # forza = prova a mano


def test_anteprima_e_prova(ambiente) -> None:
    ntfy = _Ntfy()
    anteprima = av.esegui(object(), DOMENICA_7_30, anteprima=True, opener=ntfy)
    assert anteprima["inviato"] is False and anteprima["motivo"] == "anteprima" and "Afila 3 SET" in anteprima["messaggio"]
    assert ntfy.inviati == []
    prova = av.esegui(object(), datetime(2026, 10, 19, 15, 0, tzinfo=TZ), prova=True, opener=ntfy)   # a qualunque ora
    assert prova["inviato"] is True and ntfy.inviati[0][2]["title"] == "Prova avviso semine"
    assert ambiente == [date(2026, 10, 18)]                      # la prova non legge il piano (solo l'anteprima l'ha letto)


def test_errori_leggibili(ambiente, monkeypatch) -> None:
    ntfy = _Ntfy()
    ntfy.stato = 500
    with pytest.raises(av.AvvisoNonPossibile, match="500"):
        av.esegui(object(), DOMENICA_7_30, opener=ntfy)

    def giu(richiesta, timeout=None):
        if isinstance(richiesta, str):
            return _Risposta("")
        raise OSError("connessione rifiutata")

    with pytest.raises(av.AvvisoNonPossibile, match="Avviso non inviato: connessione rifiutata"):
        av.esegui(object(), DOMENICA_7_30, opener=giu)
    monkeypatch.delenv("NTFY_TOPIC")
    with pytest.raises(av.AvvisoNonPossibile, match="NTFY_TOPIC"):
        av.esegui(object(), DOMENICA_7_30, opener=_Ntfy())
    assert av.esegui(object(), DOMENICA_7_30, anteprima=True, opener=_Ntfy())["inviato"] is False   # l'anteprima non ne ha bisogno


def test_il_modulo_non_scrive_sul_database() -> None:
    sorgente = open(av.__file__, encoding="utf-8").read().upper()
    for vietato in ("INSERT ", "UPDATE ", "DELETE ", "_CONNECT(", "EXECUTE("):
        assert vietato not in sorgente


def _client(monkeypatch):
    monkeypatch.setenv("DIARIO_PASSWORD", "segreta")
    monkeypatch.setattr(app_module, "_settings", lambda: object())
    return TestClient(app_module.app)


def test_route_richiede_la_password_e_inoltra_le_opzioni(monkeypatch) -> None:
    client = _client(monkeypatch)
    assert client.post("/api/avviso-semine").status_code == 401
    visti = []
    monkeypatch.setattr(av, "esegui", lambda settings, **kw: visti.append(kw) or {"inviato": False, "motivo": "anteprima"})
    r = client.post("/api/avviso-semine?anteprima=1&forza=1", auth=AUTH)
    assert r.status_code == 200 and r.json()["motivo"] == "anteprima"
    assert visti == [{"anteprima": True, "prova": False, "forza": True}]
    assert client.get("/api/avviso-semine", auth=AUTH).status_code == 405       # solo POST: nessun invio da un link


def test_route_errori_leggibili(monkeypatch) -> None:
    client = _client(monkeypatch)

    def senza_canale(settings, **kw):
        raise av.AvvisoNonPossibile("NTFY_TOPIC non impostata")

    monkeypatch.setattr(av, "esegui", senza_canale)
    r = client.post("/api/avviso-semine", auth=AUTH)
    assert r.status_code == 503 and r.json() == {"inviato": False, "errore": "NTFY_TOPIC non impostata"}

    def database_giu(settings, **kw):
        raise RuntimeError("database spento")

    monkeypatch.setattr(av, "esegui", database_giu)
    r = client.post("/api/avviso-semine", auth=AUTH)
    assert r.status_code == 503 and "database spento" in r.json()["errore"]
