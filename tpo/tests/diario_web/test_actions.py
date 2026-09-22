"""Test del modulo diario_web/actions.py -- solo logica pura (calcolo dei
passi di transizione, calcolo grammi, gestione dei casi ambigui), senza
toccare un database reale: le funzioni di lettura (db_context) sono
sostituite con dei doppi di test (monkeypatch), come già fatto altrove nel
repository per isolare l'Application layer dall'infrastruttura.

Nota per chi esegue questi test: coprono solo la logica del diario, non
sostituiscono i test di integrazione Postgres reale già richiesti da D5
del freeze OPERATIONAL_WEB_ADAPTER per ogni comando (`semina commission`/
`semina transition` restano coperti dai test esistenti in
tests/application e tests/integration/postgresql -- questo modulo li
richiama soltanto, non li duplica).
"""
from decimal import Decimal

import pytest

from src.tpo_core.diario_web import actions, db_context


class _SettingsFinte:
    """Le funzioni di actions.py accettano `settings` solo per passarlo a
    db_context, che qui è sostituito: un oggetto qualsiasi basta."""


def _semina(public_id="SEM-000099", stato="AVVIATA", version=0):
    return db_context.SeminaAttiva(
        public_id=public_id, stato=stato, version=version,
        codice_tracciabilita="XXX-0101-A", data_avvio="2026-09-21T09:00:00+01:00",
    )


def _candidato(lse="LSE-000099", grammi_per_set="14", residuo="500", anomalia=None):
    return db_context.LottoProtocolloCandidato(
        lotto_seme_public_id=lse, lotto_seme_version=1, fornitore="Golinucci Organic",
        referenza_commerciale="Test", quantita_residua=Decimal(residuo),
        protocollo_versione_public_id="PV-000099",
        grammi_seme_per_set=Decimal(grammi_per_set), anomalia=anomalia,
    )


# --- prepara_transition ---------------------------------------------------

def test_transition_un_solo_passo(monkeypatch):
    monkeypatch.setattr(db_context, "semine_attive_per_varieta",
                         lambda settings, vid: [_semina(stato="GERMINAZIONE")])
    proposta = actions.prepara_transition(_SettingsFinte(), "VAR-000004", "Mizuna", "LUCE")
    assert [p.stato for p in proposta.passi] == ["LUCE"]
    assert proposta.semina_public_id == "SEM-000099"


def test_transition_piu_passi_intermedi(monkeypatch):
    monkeypatch.setattr(db_context, "semine_attive_per_varieta",
                         lambda settings, vid: [_semina(stato="AVVIATA")])
    proposta = actions.prepara_transition(_SettingsFinte(), "VAR-000004", "Mizuna", "CRESCITA")
    assert [p.stato for p in proposta.passi] == ["GERMINAZIONE", "LUCE", "CRESCITA"]


def test_transition_nessuna_semina_attiva(monkeypatch):
    monkeypatch.setattr(db_context, "semine_attive_per_varieta", lambda settings, vid: [])
    with pytest.raises(actions.SeminaNonTrovata):
        actions.prepara_transition(_SettingsFinte(), "VAR-000002", "Rábano", "LUCE")


def test_transition_piu_semine_attive_e_ambiguo(monkeypatch):
    monkeypatch.setattr(
        db_context, "semine_attive_per_varieta",
        lambda settings, vid: [_semina(public_id="SEM-000001"), _semina(public_id="SEM-000002")],
    )
    with pytest.raises(actions.PropostaAmbigua):
        actions.prepara_transition(_SettingsFinte(), "VAR-000004", "Mizuna", "LUCE")


def test_transition_stato_gia_raggiunto(monkeypatch):
    monkeypatch.setattr(db_context, "semine_attive_per_varieta",
                         lambda settings, vid: [_semina(stato="LUCE")])
    with pytest.raises(actions.PropostaAmbigua):
        actions.prepara_transition(_SettingsFinte(), "VAR-000004", "Mizuna", "GERMINAZIONE")


def test_transition_stato_non_riconosciuto(monkeypatch):
    monkeypatch.setattr(db_context, "semine_attive_per_varieta",
                         lambda settings, vid: [_semina()])
    with pytest.raises(actions.PropostaAmbigua):
        actions.prepara_transition(_SettingsFinte(), "VAR-000004", "Mizuna", "NON_ESISTE")


# --- prepara_commission -----------------------------------------------------

def test_commission_calcola_grammi_da_protocollo(monkeypatch):
    monkeypatch.setattr(db_context, "candidati_lotto_protocollo",
                         lambda settings, vid: [_candidato(grammi_per_set="14", residuo="500")])
    proposta = actions.prepara_commission(
        _SettingsFinte(), "VAR-000002", "Rábano", "3", "RIPRISTINO_STOCK", None,
    )
    assert proposta.grammi == "42"
    assert proposta.residuo_dopo == "458"


def test_commission_nessun_candidato(monkeypatch):
    monkeypatch.setattr(db_context, "candidati_lotto_protocollo", lambda settings, vid: [])
    with pytest.raises(actions.PropostaAmbigua):
        actions.prepara_commission(_SettingsFinte(), "VAR-000002", "Rábano", "1", "RIPRISTINO_STOCK", None)


def test_commission_candidati_multipli(monkeypatch):
    monkeypatch.setattr(
        db_context, "candidati_lotto_protocollo",
        lambda settings, vid: [_candidato(lse="LSE-000010"), _candidato(lse="LSE-000019")],
    )
    with pytest.raises(actions.PropostaAmbigua):
        actions.prepara_commission(_SettingsFinte(), "VAR-000002", "Rábano", "1", "RIPRISTINO_STOCK", None)


def test_commission_lotto_con_anomalia_escluso(monkeypatch):
    monkeypatch.setattr(
        db_context, "candidati_lotto_protocollo",
        lambda settings, vid: [_candidato(anomalia="nota qualunque")],
    )
    with pytest.raises(actions.PropostaAmbigua):
        actions.prepara_commission(_SettingsFinte(), "VAR-000002", "Rábano", "1", "RIPRISTINO_STOCK", None)


def test_commission_seme_insufficiente(monkeypatch):
    monkeypatch.setattr(db_context, "candidati_lotto_protocollo",
                         lambda settings, vid: [_candidato(grammi_per_set="14", residuo="10")])
    with pytest.raises(actions.PropostaAmbigua):
        actions.prepara_commission(_SettingsFinte(), "VAR-000002", "Rábano", "1", "RIPRISTINO_STOCK", None)


# --- esegui_* costruiscono il Namespace atteso da run_semina_command -------

def test_esegui_transition_passa_i_campi_giusti(monkeypatch):
    catturati = []

    def _finto_run_semina_command(args, *, stdout, stderr):
        catturati.append(args)
        stdout.write("STATUS: INSERTED\n")
        return 0

    monkeypatch.setattr(actions, "run_semina_command", _finto_run_semina_command)
    monkeypatch.setattr(db_context, "semine_attive_per_varieta",
                         lambda settings, vid: [_semina(stato="GERMINAZIONE", version=1)])
    proposta = actions.PropostaTransition(
        varieta_public_id="VAR-000004", semina_public_id="SEM-000099", varieta_nome="Mizuna",
        stato_attuale="GERMINAZIONE", passi=[actions.PassoTransizione(stato="LUCE")],
    )
    esito = actions.esegui_transition(_SettingsFinte(), proposta, "giulia@towerpower")
    assert "INSERTED" in esito
    assert len(catturati) == 1
    args = catturati[0]
    assert args.semina_command == "transition"
    assert args.semina == "SEM-000099"
    assert args.expected_semina_version == 1
    assert args.target_state == "LUCE"
    assert args.actor == "giulia@towerpower"
    assert args.confirm is True


def test_esegui_transition_fallita_solleva_eccezione(monkeypatch):
    def _finto_run_semina_command(args, *, stdout, stderr):
        stderr.write("SEMINA_LIFECYCLE_FAILED: SEMINA_LIFECYCLE_TIMESTAMP_REGRESSION: test\n")
        return 1

    monkeypatch.setattr(actions, "run_semina_command", _finto_run_semina_command)
    monkeypatch.setattr(db_context, "semine_attive_per_varieta",
                         lambda settings, vid: [_semina(stato="GERMINAZIONE", version=1)])
    proposta = actions.PropostaTransition(
        varieta_public_id="VAR-000004", semina_public_id="SEM-000099", varieta_nome="Mizuna",
        stato_attuale="GERMINAZIONE", passi=[actions.PassoTransizione(stato="LUCE")],
    )
    with pytest.raises(actions.SeminaOperazioneFallita):
        actions.esegui_transition(_SettingsFinte(), proposta, "giulia@towerpower")
