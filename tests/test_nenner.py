"""Der Bericht muss seinen Nenner nennen — und den Empfaenger nicht brechen.

WARUM DIESE DATEI EXISTIERT (2026-08-10, Brain):
Seit Kat D und E `NICHT GEMESSEN` melden statt still `[]` zurueckzugeben, zaehlt
`total findings` zwei Sorten in eine Zahl: echte Befunde und ungebaute Pruefungen.
Gemessen am Cluster-Bestand: 63 = 61 echte + 2 Nicht-Messungen. Werden D und E
gebaut, sinkt die Zahl um 2 und sieht aus wie Fortschritt bei den Befunden.
Das ist ein Aggregat ohne Nenner (Non-Negotiable 2).

Die zweite Haelfte ist wichtiger als die erste: `- total findings: N` ist ein
VERTRAG. Zwei Empfaenger binden darauf, beide ausserhalb dieses Repos. Bricht die
Zeile, liefert der Shim leeren Klartext, und melde.sh postet bei Exit 1 dann gar
nichts (Template-Guard, TASK-2026-01100). Ein Waechter, der still wird, weil sein
Absender schoener formatiert — genau der Fehler, gegen den hier geprueft wird.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import kb_lint  # noqa: E402


# Woertlich die Sonden der beiden Empfaenger, abgeschrieben am 2026-08-10:
#   /opt/scripts/kb-lint-befunde.py:58
#   /opt/aie-watchers/kb-lint-watcher-shim.sh  (sed -n "s/^- total findings: /...")
EMPFAENGER_REGEX = re.compile(r"^- total findings: (\d+)", re.M)
EMPFAENGER_SED_PREFIX = "- total findings: "
UEBERSPRUNGEN_REGEX = re.compile(r"^- uebersprungen \(nicht pruefbar\): (\d+)", re.M)


@pytest.fixture()
def kb_tmp(tmp_path: Path) -> Path:
    for sub in ("ops", "projects", "wiki", "raw"):
        (tmp_path / sub).mkdir()
    (tmp_path / "ops" / "eine.md").write_text(
        "---\nstand: 2026-08-10\nmutability: mutable-mit-stand\nclassification: internal\n---\n# Inhalt\n",
        encoding="utf-8",
    )
    # Kat G (seit 2026-08-21) misst ops/KNOWN-ERRORS-DB.md — eine saubere Mini-KEDB,
    # damit G als GEMESSEN zaehlt und nur D/E die Ungebauten bleiben.
    (tmp_path / "ops" / "KNOWN-ERRORS-DB.md").write_text(
        "# KEDB\n## Teil C — Index (1 gelernte Korrekturen)\n| KE | F |\n|---|---|\n| a | b |\n## Teil A\n## KE-2026-01-01-A — x\n"
    )
    # Kat H (seit 2026-08-21) misst .live gegen registries/senken.yaml — eine saubere
    # Mini-Lage, damit H als GEMESSEN zaehlt und nur D/E die Ungebauten bleiben.
    (tmp_path / "control-plane" / "registries").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control-plane" / "registries" / "senken.yaml").write_text(
        "senken:\n  - muster: \"a-*.json\"\n    schreiber: x\n    leser: y\n"
    )
    (tmp_path / ".live").mkdir(exist_ok=True)
    (tmp_path / ".live" / "a-1.json").write_text("{}")
    return tmp_path


# ---------------- Der Vertrag zum Empfaenger ----------------

def test_total_findings_zeile_bleibt_woertlich_lesbar(kb_tmp: Path):
    """Die Zeile, auf die zwei fremde Programme binden, bleibt erkennbar."""
    md = kb_lint.format_markdown(kb_lint.run_lint(kb_tmp))
    treffer = EMPFAENGER_REGEX.search(md)
    assert treffer is not None, (
        "kb-lint-befunde.py:58 findet die Befundzahl nicht mehr — der Waechter "
        "wuerde mit 'LAUFFEHLER: der Bericht nennt keine Befundzahl' abbrechen."
    )
    assert any(z.startswith(EMPFAENGER_SED_PREFIX) for z in md.splitlines()), (
        "Das sed im Shim greift nicht mehr — LAGE waere leer, und ein leerer "
        "Klartext bei Exit 1 heisst: kein Post."
    )


def test_uebersprungen_zeile_bleibt_woertlich_lesbar(kb_tmp: Path):
    md = kb_lint.format_markdown(kb_lint.run_lint(kb_tmp))
    assert UEBERSPRUNGEN_REGEX.search(md) is not None


def test_befundzahl_im_bericht_stimmt_mit_total_ueberein(kb_tmp: Path):
    """Was der Empfaenger liest, ist was der Bericht meint."""
    report = kb_lint.run_lint(kb_tmp)
    md = kb_lint.format_markdown(report)
    assert int(EMPFAENGER_REGEX.search(md).group(1)) == report.total()


# ---------------- Der Nenner ----------------

def test_kategorien_zeile_nennt_nenner_und_die_ungebauten(kb_tmp: Path):
    md = kb_lint.format_markdown(kb_lint.run_lint(kb_tmp))
    assert "- Kategorien: 6 von 8 gemessen · 2 NICHT GEBAUT (D, E)" in md


def test_nicht_gemessene_kategorien_werden_namentlich_genannt(kb_tmp: Path):
    assert kb_lint.run_lint(kb_tmp).kategorien_nicht_gemessen() == ["D", "E"]


def test_echte_befunde_zaehlen_nichtmessungen_nicht_mit(kb_tmp: Path):
    report = kb_lint.run_lint(kb_tmp)
    # D und E liefern je genau eine Nicht-Messung.
    assert report.befunde_echt() == report.total() - 2


def test_aufteilungszeile_erscheint_nur_wenn_beide_sorten_vorkommen(kb_tmp: Path):
    md = kb_lint.format_markdown(kb_lint.run_lint(kb_tmp))
    assert "- davon echte Befunde:" in md


def test_to_dict_traegt_den_nenner_mit(kb_tmp: Path):
    d = kb_lint.run_lint(kb_tmp).to_dict()
    assert d["kategorien_gesamt"] == 8
    assert d["kategorien_gemessen"] == 6
    assert d["kategorien_nicht_gemessen"] == ["D", "E"]
    assert d["befunde_echt"] == d["total_findings"] - 2


# ---------------- Der Fall, in dem eine Kategorie beides ist ----------------

def test_kat_d_kann_zugleich_ungemessen_und_fuendig_sein(kb_tmp: Path):
    """Die fehlende Kaskaden-Analyse verdeckt den echten Fund nicht — und umgekehrt."""
    (kb_tmp / ".provenance").mkdir()
    (kb_tmp / ".provenance" / "quarantine.json").write_text("{}", encoding="utf-8")

    report = kb_lint.run_lint(kb_tmp)
    kat_d = report.kat_d

    assert sum(1 for f in kat_d if not f.gemessen) == 1, "die Nicht-Messung fehlt"
    assert sum(1 for f in kat_d if f.gemessen) == 1, "der echte Befund fehlt"
    # D bleibt als ungebaut gefuehrt, obwohl es etwas gefunden hat.
    assert "D" in report.kategorien_nicht_gemessen()
    # und der echte Fund zaehlt als echter Fund.
    assert report.befunde_echt() == report.total() - 2


# ---------------- Positivkontrolle ----------------

def test_ohne_ungebaute_kategorien_nennt_die_zeile_acht_von_acht():
    """Sonst wuerde '4 von 6' auch dann stehen, wenn alles gemessen waere —
    und die Zeile bewiese nichts."""
    report = kb_lint.LintReport(started="t", kb_root="/x")
    report.kat_a = [kb_lint.Finding(kat="A", path="p", detail="d")]
    md = kb_lint.format_markdown(report)
    assert "- Kategorien: 8 von 8 gemessen" in md
    assert "NICHT GEBAUT" not in md
    assert "- davon echte Befunde:" not in md
