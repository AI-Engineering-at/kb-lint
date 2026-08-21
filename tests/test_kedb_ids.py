"""Kat G — KEDB-Hygiene: eindeutige KE-IDs und eine Bestandszahl, die stimmt.

ANLASS (TASK-2026-01441, fio, 2026-08-21): 8 IDs kamen je zweimal mit verschiedenen Titeln
vor (KE-2026-08-10-A..G, KE-2026-08-13-B), die Teil-C-Ueberschrift sagte 29 bei 31 Zeilen.
Die KEDB verlangt eindeutige IDs und prueft sie nicht — eine Regel als Prosa. Jetzt misst
sie jemand. Beide Richtungen: Kollision MUSS gemeldet werden, saubere Datei darf NICHT.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import kb_lint

SAUBER = """# KEDB
## Teil C — Memory-Pattern-Index (2 gelernte Korrekturen — Pointer, kein Duplikat)
| KE | Falle |
|---|---|
| x | a |
| y | b |
## Teil A
## KE-2026-08-10-A — erster
text
### KE-2026-08-10-B — zweiter
### Nachtrag zu KE-2026-08-10-A — Nachtrag zaehlt nicht als neue ID
"""

def _kb(tmp_path, text):
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "KNOWN-ERRORS-DB.md").write_text(text, encoding="utf-8")
    return tmp_path

def test_saubere_kedb_liefert_keinen_befund(tmp_path):
    f = kb_lint.kat_g_kedb_hygiene(_kb(tmp_path, SAUBER))
    assert [x for x in f if x.gemessen] == [], [x.detail for x in f]

def test_kollision_wird_gemeldet_mit_zeilen(tmp_path):
    text = SAUBER + "## KE-2026-08-10-A — dritter, gleiche ID, anderer Titel\n"
    f = kb_lint.kat_g_kedb_hygiene(_kb(tmp_path, text))
    treffer = [x for x in f if "KE-2026-08-10-A" in x.detail]
    assert len(treffer) == 1 and treffer[0].severity == "error"
    assert "Z." in treffer[0].detail and "2" in treffer[0].detail, treffer[0].detail

def test_teil_c_zahl_gegen_tabellenzeilen(tmp_path):
    text = SAUBER.replace("2 gelernte Korrekturen", "29 gelernte Korrekturen")
    f = kb_lint.kat_g_kedb_hygiene(_kb(tmp_path, text))
    treffer = [x for x in f if "Teil C" in x.detail]
    assert len(treffer) == 1 and "29" in treffer[0].detail and "2" in treffer[0].detail

def test_fehlende_kedb_ist_nicht_gemessen_nicht_sauber(tmp_path):
    f = kb_lint.kat_g_kedb_hygiene(tmp_path)
    assert len(f) == 1 and f[0].gemessen is False

def test_kat_g_laeuft_im_runner_und_zaehlt(tmp_path):
    kb = _kb(tmp_path, SAUBER + "## KE-2026-08-10-A — dritter\n")
    r = kb_lint.run_lint(kb, scan_dirs=["ops"])
    assert any("KE-2026-08-10-A" in x.detail for x in r.kat_g)
    assert r.total() >= 1 and "Kat G" in kb_lint.format_markdown(r)
