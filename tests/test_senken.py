"""Kat H — Senke ohne Leser (Gate D, TASK-2026-01438).

Drei Fragen an kb/.live gegen control-plane/registries/senken.yaml:
  1. Passt jede Datei auf ein muster?              sonst: Senke ohne Eintrag
  2. Hat jeder Eintrag einen Leser?                 "—" nur mit entscheidung_bis; danach error
  3. Schreibt der Schreiber noch? (takt_stunden)    juengste Datei aelter als 3 Takte: still
Beide Richtungen: eine saubere Lage liefert 0, jede Luecke genau einen Befund.
"""
import sys, pathlib, datetime as dt
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import kb_lint

REG = """stand: 2026-08-21
senken:
  - muster: "antistillstand-*.jsonl"
    klasse: bericht
    schreiber: x
    takt_stunden: 24
    leser: "brain-next-step"
  - muster: "*-rueckbau-*.json"
    klasse: rueckbau
    schreiber: fio
    leser: "Mensch bei Rueckbau"
  - muster: "supply-chain-report-*"
    klasse: bericht
    schreiber: y
    leser: "—"
    entscheidung_bis: {bis}
  - muster: "{{brain-chain,eval}}/**"
    klasse: bericht
    schreiber: z
    leser: "NICHT GEMESSEN"
    entscheidung_bis: {bis}
"""

REG_SAUBER = "\n".join(REG.splitlines()[:11]) + "\n  - muster: \"{{brain-chain,eval}}/**\"\n    klasse: bericht\n    schreiber: z\n    leser: \"audit\"\n"


def _kb(tmp_path, bis="2099-01-01", dateien=(), reg=None):
    (tmp_path / "control-plane" / "registries").mkdir(parents=True)
    (tmp_path / "control-plane" / "registries" / "senken.yaml").write_text((reg or REG).format(bis=bis))
    live = tmp_path / ".live"; live.mkdir()
    for name in dateien:
        p = live / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text("x")
    return tmp_path

HEUTE = dt.date(2026, 8, 21)

def _befunde(kb):
    return [f for f in kb_lint.kat_h_senken(kb, today=HEUTE) if f.gemessen]

def test_saubere_lage_liefert_nichts(tmp_path):
    # sauber = jede Datei hat einen Eintrag UND jeder Eintrag einen Leser — ein Eintrag
    # ohne Leser ist selbst ein Befund, auch vor seiner Entscheidungsfrist
    kb = _kb(tmp_path, dateien=["antistillstand-2026-08-21.jsonl", "fristen-setzen-rueckbau-1.json",
                                "brain-chain/2026-08-21/chain.json", "eval/x.txt"], reg=REG_SAUBER)
    assert _befunde(kb) == [], [f.detail for f in _befunde(kb)]

def test_datei_ohne_eintrag_wird_gemeldet(tmp_path):
    kb = _kb(tmp_path, dateien=["antistillstand-2026-08-21.jsonl", "neuer-report.md", "neuer-ordner/a.txt"])
    d = [f.detail for f in _befunde(kb)]
    assert any("neuer-report.md" in x and "ohne Eintrag" in x for x in d), d
    assert any("neuer-ordner" in x and "ohne Eintrag" in x for x in d), d

def test_ohne_leser_ist_warn_bis_frist_dann_error(tmp_path):
    kb = _kb(tmp_path, bis="2026-08-31", dateien=["supply-chain-report-1.md", "antistillstand-2026-08-21.jsonl"])
    f = [x for x in _befunde(kb) if "supply-chain-report" in x.detail]
    assert len(f) == 1 and f[0].severity == "warn" and "2026-08-31" in f[0].detail, [x.detail for x in f]
    kb2 = _kb(tmp_path / "b", bis="2026-08-01", dateien=["supply-chain-report-1.md", "antistillstand-2026-08-21.jsonl"])
    f2 = [x for x in _befunde(kb2) if "supply-chain-report" in x.detail]
    assert len(f2) == 1 and f2[0].severity == "error"

def test_stiller_schreiber_wird_gemeldet(tmp_path):
    # juengste antistillstand-Datei vom 09.08., Takt 24 h -> 12 Tage still
    kb = _kb(tmp_path, dateien=["antistillstand-2026-08-09.jsonl", "antistillstand-2026-08-08.jsonl"])
    f = [x for x in _befunde(kb) if "still" in x.detail]
    assert len(f) == 1 and "antistillstand" in f[0].detail and "12" in f[0].detail, [x.detail for x in _befunde(kb)]

def test_ohne_registry_nicht_gemessen(tmp_path):
    (tmp_path / ".live").mkdir()
    f = kb_lint.kat_h_senken(tmp_path, today=HEUTE)
    assert len(f) == 1 and f[0].gemessen is False

def test_kat_h_im_runner_und_bericht(tmp_path):
    kb = _kb(tmp_path, dateien=["neuer-report.md"])
    r = kb_lint.run_lint(kb, scan_dirs=["ops"], today=HEUTE)
    assert any("ohne Eintrag" in x.detail for x in r.kat_h)
    assert "Kat H" in kb_lint.format_markdown(r)
