"""Protocolli nuovi Cavolo rosso / Girasole (12/10/2026): piano, valori dichiarati vs copiati, controlli, comandi."""
import importlib.util
import sys
from datetime import time
from decimal import Decimal
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "commissioning" / "2026-10-12_protocolli_nuovi.py"


def _module():
    spec = importlib.util.spec_from_file_location("protocolli_nuovi_12_10", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PAK = ("VAR-000008", "Pak Choi", "Pak Choi White", "MICROGREEN", "Microgreen", "Protocollo Pak Choi White",
       time(9, 0), time(8, 0), Decimal("1"), Decimal("1"), 1, 30, "PV-000010", 7)


class FakeCtx:
    execute = False

    def __init__(self, sementi=None, impieghi=(), protocolli=None, lead_min=1):
        self.calls = []
        self.sementi = sementi if sementi is not None else [
            (16, "Hyfarm", "Col Roja (Cavolo rosso)", Decimal("740")), (17, "Hyfarm", "Girasoli (Sunflower)", Decimal("20"))]
        self.impieghi = set(impieghi)
        self.protocolli = protocolli if protocolli is not None else [PAK[:10] + (lead_min, 30, "PV-000010", 7)]

    def check_head(self): pass

    def q(self, sql, args=()):
        if "FROM tpo.varieta" in sql:
            return [("VAR-000008", "Pak Choi"), ("VAR-000012", "Cavolo rosso"), ("VAR-000013", "Girasole")]
        if "protocollo_versioni pv" in sql:
            return self.protocolli
        if sql.strip().startswith("SELECT public_id FROM tpo.protocollo_versioni"):
            return [("PV-000010",), ("PV-000011",)] + [(r[12],) for r in self.protocolli]
        if "FROM tpo.sementi" in sql:
            return self.sementi
        raise AssertionError(sql)

    def one(self, sql, args=()):
        return (1,) if (args[0], args[1]) in self.impieghi else None

    def tpo(self, args, label):
        self.calls.append(args)
        return ""


def _arg(call, name):
    return call[call.index(name) + 1]


def test_plan_uses_declared_values_and_copies_the_rest_from_pak_choi(capsys):
    module = _module()
    ctx = FakeCtx()
    assert module.run(ctx) == 0
    protocolli = [c for c in ctx.calls if c[0] == "protocollo"]
    cavolo, girasole = protocolli
    assert (_arg(cavolo, "--variety-id"), _arg(cavolo, "--protocol-version-id")) == ("VAR-000012", "PV-000012")
    assert (_arg(girasole, "--variety-id"), _arg(girasole, "--protocol-version-id")) == ("VAR-000013", "PV-000013")
    assert [_arg(cavolo, o) for o in ("--hydration-hours", "--germination-days", "--light-growth-days",
                                      "--seed-grams-per-set", "--harvest-max-lead-days")] == ["0", "4", "8", "10", "8"]
    assert [_arg(girasole, o) for o in ("--hydration-hours", "--germination-days", "--light-growth-days",
                                        "--seed-grams-per-set", "--harvest-max-lead-days")] == ["12", "6", "6", "28", "5"]
    for c in protocolli:     # i campi non dichiarati vengono dal modello
        assert (_arg(c, "--harvest-min-lead-days"), _arg(c, "--temporal-buffer-minutes"), _arg(c, "--expected-yield"),
                _arg(c, "--planned-sowing-time"), _arg(c, "--target-harvest-time")) == ("1", "30", "1", "09:00:00", "08:00:00")
        assert _arg(c, "--productive-use-code") == "MICROGREEN" and _arg(c, "--version") == "1"
        assert _arg(c, "--valid-from") == "2026-10-12"
    assert (_arg(cavolo, "--cultivar-name"), _arg(cavolo, "--protocol-name")) == ("Cavolo rosso", "Protocollo Cavolo rosso")
    assert {_arg(c, "--actor") for c in protocolli} == {"tpo.owner"}      # lo stesso attore che creo' l'uso "Microgreens"
    impieghi = [c for c in ctx.calls if c[0] == "semente-impiego"]
    assert [(_arg(c, "--referenza-commerciale"), _arg(c, "--protocol-version"), _arg(c, "--raccomandazione")) for c in impieghi] == [
        ("Col Roja (Cavolo rosso)", "PV-000012", "RACCOMANDATA"), ("Girasoli (Sunflower)", "PV-000013", "RACCOMANDATA")]
    out = capsys.readouterr().out
    assert "copiati da Pak Choi" in out and "ATTENZIONE: il seme a magazzino (20 g) non basta per 1 SET (28 g)" in out
    assert "COMANDO CORRETTIVO" in out and "2026-10-07_revisiona_protocollo.py" in out


def test_rerun_skips_what_exists():
    module = _module()
    esistente = ("VAR-000012", "Cavolo rosso", "Cavolo rosso", "MICROGREEN", "Microgreen", "Protocollo Cavolo rosso",
                 time(9, 0), time(8, 0), Decimal("1"), Decimal("1"), 1, 30, "PV-000012", 7)
    ctx = FakeCtx(impieghi={(16, "VAR-000012")}, protocolli=[PAK, esistente])
    module.run(ctx)
    assert [_arg(c, "--variety-id") for c in ctx.calls if c[0] == "protocollo"] == ["VAR-000013"]
    assert [_arg(c, "--protocol-version") for c in ctx.calls if c[0] == "semente-impiego"] == ["PV-000013"]


def test_stops_when_copied_minimum_lead_exceeds_declared_or_seed_is_ambiguous():
    module = _module()
    b = module.carica_base()
    with pytest.raises(b.Stop, match="anticipo minimo"):
        module.run(FakeCtx(lead_min=6))
    ambigua = [(16, "Hyfarm", "Col Roja", Decimal("740")), (18, "Altro", "Cavolo rosso bio", Decimal("100")),
               (17, "Hyfarm", "Girasoli", Decimal("100"))]
    with pytest.raises(b.Stop, match="trovate 2 sementi"):
        module.run(FakeCtx(sementi=ambigua))
    with pytest.raises(b.Stop, match="nessuna"):
        module.run(FakeCtx(sementi=[(17, "Hyfarm", "Girasoli", Decimal("100"))]))


class FakeCtxLenticchia(FakeCtx):
    def __init__(self):
        super().__init__(sementi=[(18, "Hyfarm", "Lenticchie (Lentils)", Decimal("660"))])

    def q(self, sql, args=()):
        if "FROM tpo.varieta" in sql:
            return [("VAR-000008", "Pak Choi"), ("VAR-000014", "Lenticchia")]
        return super().q(sql, args)


def test_a_single_custom_variety_with_its_own_validity_date(capsys):
    from datetime import date
    module = _module()
    ctx = FakeCtxLenticchia()
    nuovi = [{"nome": "Lenticchia", "idratazione": Decimal("12"), "germinazione": 3, "luce": 6, "g_per_set": Decimal("40"),
              "lead_max": 8, "valido_dal": date(2026, 10, 13), "seme": ("lenticch", "lentil")}]
    assert module.run(ctx, nuovi=nuovi) == 0
    [protocollo] = [c for c in ctx.calls if c[0] == "protocollo"]
    assert (_arg(protocollo, "--variety-id"), _arg(protocollo, "--valid-from")) == ("VAR-000014", "2026-10-13")
    assert [_arg(protocollo, o) for o in ("--hydration-hours", "--germination-days", "--light-growth-days",
                                           "--seed-grams-per-set", "--harvest-max-lead-days")] == ["12", "3", "6", "40", "8"]
    assert [_arg(c, "--referenza-commerciale") for c in ctx.calls if c[0] == "semente-impiego"] == ["Lenticchie (Lentils)"]
    assert "valido dal 2026-10-13" in capsys.readouterr().out


def test_undeclared_delivery_limit_is_copied_from_the_model_and_shown_as_copied(capsys):
    from datetime import date
    module = _module()
    ctx = FakeCtxLenticchia()
    nuovi = [{"nome": "Lenticchia", "idratazione": Decimal("12"), "germinazione": 3, "luce": 6, "g_per_set": Decimal("40"),
              "lead_max": None, "valido_dal": date(2026, 10, 13), "seme": ("lenticch", "lentil")}]
    assert module.run(ctx, nuovi=nuovi) == 0
    [protocollo] = [c for c in ctx.calls if c[0] == "protocollo"]
    assert _arg(protocollo, "--harvest-max-lead-days") == "7"       # dal modello (Pak Choi), non inventato
    out = capsys.readouterr().out
    assert "consegna entro 7 gg dalla raccolta (non dichiarato)" in out
